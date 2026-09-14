"""Regression tests for the standalone four-operation package."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

# When discovery is launched from inside the package directory, Python needs
# the package's parent on sys.path in order to import pud_operation_generator.
ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from pud_operation_generator import (
    build_e4m3_add,
    build_e4m3_mul,
    build_e5m2_add,
    build_e5m2_mul,
    build_int8_add,
    build_int8_mul,
    build_uint8_add,
    build_uint8_mul,
)
from pud_operation_generator.__main__ import BUILDERS
from pud_operation_generator.artifacts import PROFILES, write_program
from pud_operation_generator.core import Primitive, execute, pack, signed_value, unpack
from pud_operation_generator.validation import verify

class GeneratorTests(unittest.TestCase):
    def test_public_surface_contains_expected_profiles(self):
        self.assertEqual(
            list(PROFILES),
            [
                "uint8-add",
                "uint8-mul",
                "int8-add",
                "int8-mul",
                "fp8-e5m2-add",
                "fp8-e5m2-mul",
                "fp8-e4m3-add",
                "fp8-e4m3-mul",
            ],
        )

    def test_expected_primitive_counts(self):
        self.assertEqual(len(build_uint8_add().trace), 50)
        self.assertEqual(len(build_uint8_mul().trace), 608)
        self.assertEqual(len(build_int8_add().trace), 54)
        self.assertEqual(len(build_int8_mul().trace), 620)
        self.assertEqual(len(build_e5m2_add().trace), 1053)
        self.assertEqual(len(build_e5m2_mul().trace), 334)
        self.assertEqual(len(build_e4m3_add().trace), 1339)
        self.assertEqual(len(build_e4m3_mul().trace), 326)

    def test_selected_uint8_values(self):
        cases = [(0, 0), (1, 255), (127, 129), (255, 255)]
        for builder, expected in (
            (build_uint8_add, [a + b for a, b in cases]),
            (build_uint8_mul, [a * b for a, b in cases]),
        ):
            program = builder()
            lanes = len(cases)
            initial = dict(
                zip(
                    program.inputs,
                    pack([a for a, _ in cases], 8)
                    + pack([b for _, b in cases], 8),
                )
            )
            initial.update(
                {
                    row: (1 << lanes) - 1 if value else 0
                    for row, value in program.constants.items()
                }
            )
            rows = execute(program.trace, initial, lanes)
            actual = unpack([rows[row] for row in program.outputs["R"]], lanes)
            self.assertEqual(actual, expected)

    def test_selected_int8_values(self):
        cases = [(-128, -128), (-128, -1), (-128, 127), (-7, 13),
                 (-1, 0), (0, 127), (127, 127)]
        for builder, expected in (
            (build_int8_add, [a + b for a, b in cases]),
            (build_int8_mul, [a * b for a, b in cases]),
        ):
            program = builder()
            lanes = len(cases)
            initial = dict(
                zip(
                    program.inputs,
                    pack([a & 0xFF for a, _ in cases], 8)
                    + pack([b & 0xFF for _, b in cases], 8),
                )
            )
            initial.update(
                {
                    row: (1 << lanes) - 1 if value else 0
                    for row, value in program.constants.items()
                }
            )
            rows = execute(program.trace, initial, lanes)
            raw = unpack([rows[row] for row in program.outputs["R"]], lanes)
            self.assertEqual(raw, [value & 0xFF for value in expected])
            full = program.taps["full_result"]
            actual = [signed_value(value, len(full))
                      for value in unpack([rows[row] for row in full], lanes)]
            self.assertEqual(actual, expected)

    def test_target_profiles_have_exactly_eight_visible_rows(self):
        for name, factory in BUILDERS.items():
            if name.startswith(("int8-", "fp8-")):
                with self.subTest(name=name):
                    program = factory()
                    outputs = [f"R{bit}" for bit in range(8)]
                    self.assertEqual(program.outputs, {"R": outputs})
                    self.assertEqual([row for row in program.rows if row.startswith("R")], outputs)
                    self.assertEqual([p.rows[1] for p in program.trace[-8:]], outputs)

    def test_int8_mul_generates_and_reduces_all_columns_in_order(self):
        self.assert_integer_mul_column_streaming(build_int8_mul())

    def test_uint8_mul_generates_and_reduces_all_columns_in_order(self):
        program = build_uint8_mul()
        self.assertEqual(program.outputs, {"R": [f"R{bit}" for bit in range(16)]})
        self.assertEqual(program.carry_beyond_output, [])
        self.assert_integer_mul_column_streaming(program)

    def assert_integer_mul_column_streaming(self, program):
        columns = []
        products = []
        for primitive in program.trace[:-len(program.outputs["R"])]:
            stage = primitive.stage.split(":")[0]
            if stage.startswith(("partial_product_", "signed_complement_")):
                i, j = map(int, stage.split("_")[-2:])
                columns.append(i + j)
                if stage.startswith("partial_product_") and primitive.op == "TRA":
                    products.append((i, j))
            else:
                self.assertTrue(stage.startswith("column_"))
                columns.append(int(stage.split("_")[1]))
            if program.one in primitive.rows:
                self.assertIn(stage, ("column_8", "column_15"))
        self.assertEqual(columns, sorted(columns))
        # UINT8 column 15 contains only the carry from column 14, so processing
        # it emits no arithmetic primitive; it is still exported as R15.
        self.assertEqual(set(columns), set(range(16 if program.signed else 15)))
        self.assertEqual(sorted(products), [(i, j) for i in range(8) for j in range(8)])
        self.assertEqual(sorted(program.complemented_partial_products),
                         [[i, j] for i in range(8) for j in range(8)
                          if program.signed and (i == 7) != (j == 7)])
        self.assertEqual([column["bit"] for column in program.columns], list(range(16)))
        if program.signed:
            self.assertEqual(len(program.taps["full_result"]), 16)
        else:
            self.assertEqual(program.columns[15], {
                "bit": 15, "input_bits_including_carries": 1,
                "three_input_adders": 0, "two_input_adders_using_zero": 0,
            })
        self.assertEqual(sum(p.op == "5RA" for p in program.trace), 57 if program.signed else 56)

    def test_discarded_high_bit_corruption_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("int8-add", "int8-mul"):
                with self.subTest(name=name):
                    program = BUILDERS[name]()
                    # Corrupt only a non-exported bit; low-byte checks still pass.
                    program.trace.insert(-8, Primitive("NOT", (program.taps["full_result"][-1],)))
                    path, info = write_program(name, program, Path(directory))
                    with self.assertRaisesRegex(AssertionError, "full arithmetic result"):
                        verify(name, program, path, info)

    def test_all_profiles_exhaustively_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name, builder in BUILDERS.items():
                program = builder()
                path, info = write_program(name, program, output)
                report = verify(name, program, path, info)
                self.assertEqual(report["pairs"], 65_536)
                self.assertEqual(report["reference_mismatches"], 0)
                if name.startswith("int8-"):
                    self.assertEqual(report["internal_reference_mismatches"], 0)
                    self.assertEqual(report["visible_low8_mismatches"], 0)
                    self.assertEqual(report["internal_result_width"], 9 if name.endswith("add") else 16)

    def test_copied_folder_works_without_sibling_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            copied = temporary_root / "pud_operation_generator"
            shutil.copytree(ROOT, copied, ignore=shutil.ignore_patterns("__pycache__"))
            output = temporary_root / "out"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pud_operation_generator",
                    "--only",
                    "int8-add",
                    "--out",
                    str(output),
                ],
                cwd=temporary_root,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("reference/replay PASS", completed.stdout)
            report = json.loads((output / "validation.json").read_text())
            self.assertEqual(list(report["variants"]), ["int8-add"])


if __name__ == "__main__":
    unittest.main()
