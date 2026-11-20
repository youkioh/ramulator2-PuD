"""Regression tests for the standalone arithmetic-profile package."""

import json
from fractions import Fraction
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
    build_e2m1_add,
    build_e2m1_mul,
    build_e5m2_add,
    build_e5m2_mul,
    build_int4_add,
    build_int4_mul,
    build_int8_add,
    build_int8_mul,
    build_uint4_add,
    build_uint4_mul,
    build_uint8_add,
    build_uint8_mul,
)
from pud_operation_generator.__main__ import BUILDERS
from pud_operation_generator.artifacts import PROFILES, write_program
from pud_operation_generator.core import Primitive, execute, pack, signed_value, unpack
from pud_operation_generator.fp8 import E2M1, normal_value
from pud_operation_generator.validation import verify

class GeneratorTests(unittest.TestCase):
    def test_public_surface_contains_expected_profiles(self):
        self.assertEqual(
            list(PROFILES),
            [
                "uint4-add",
                "uint4-mul",
                "int4-add",
                "int4-mul",
                "uint8-add",
                "uint8-mul",
                "int8-add",
                "int8-mul",
                "fp4-e2m1-add",
                "fp4-e2m1-mul",
                "fp8-e5m2-add",
                "fp8-e5m2-mul",
                "fp8-e4m3-add",
                "fp8-e4m3-mul",
            ],
        )

    def test_expected_primitive_counts(self):
        self.assertEqual(len(build_uint4_add().trace), 25)
        self.assertEqual(len(build_uint4_mul().trace), 140)
        self.assertEqual(len(build_int4_add().trace), 30)
        self.assertEqual(len(build_int4_mul().trace), 152)
        self.assertEqual(len(build_uint8_add().trace), 49)
        self.assertEqual(len(build_uint8_mul().trace), 600)
        self.assertEqual(len(build_int8_add().trace), 54)
        self.assertEqual(len(build_int8_mul().trace), 620)
        self.assertEqual(len(build_e2m1_add().trace), 485)
        self.assertEqual(len(build_e2m1_mul().trace), 126)
        self.assertEqual(len(build_e5m2_add().trace), 1053)
        self.assertEqual(len(build_e5m2_mul().trace), 334)
        self.assertEqual(len(build_e4m3_add().trace), 1339)
        self.assertEqual(len(build_e4m3_mul().trace), 326)

    def test_e2m1_encoding_contract(self):
        self.assertEqual(E2M1.total_bits, 4)
        self.assertEqual(E2M1.min_normal, 1)
        self.assertEqual(E2M1.max_normal, 6)
        self.assertEqual(
            [normal_value(code, E2M1) for code in range(2, 8)],
            [1, Fraction(3, 2), 2, 3, 4, 6],
        )
        self.assertFalse(E2M1.is_normal(0))
        self.assertFalse(E2M1.is_normal(1))
        self.assertTrue(E2M1.is_normal(7))

    def test_selected_uint4_values(self):
        cases = [(0, 0), (1, 15), (7, 9), (15, 15)]
        for builder, expected in (
            (build_uint4_add, [a + b for a, b in cases]),
            (build_uint4_mul, [a * b for a, b in cases]),
        ):
            program = builder()
            lanes = len(cases)
            initial = dict(
                zip(
                    program.inputs,
                    pack([a for a, _ in cases], 4)
                    + pack([b for _, b in cases], 4),
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
            self.assertEqual(raw, [value & 0xF for value in expected])
            full = unpack(
                [rows[row] for row in program.taps["full_result"]], lanes
            )
            self.assertEqual(full, expected)

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
            raw = unpack([rows[row] for row in program.outputs["R"]], lanes)
            self.assertEqual(raw, [value & 0xFF for value in expected])
            full = unpack(
                [rows[row] for row in program.taps["full_result"]], lanes
            )
            self.assertEqual(full, expected)

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

    def test_selected_int4_values(self):
        cases = [(-8, -8), (-8, -1), (-8, 7), (-3, 5), (-1, 0), (7, 7)]
        for builder, expected in (
            (build_int4_add, [a + b for a, b in cases]),
            (build_int4_mul, [a * b for a, b in cases]),
        ):
            program = builder()
            lanes = len(cases)
            initial = dict(
                zip(
                    program.inputs,
                    pack([a & 0xF for a, _ in cases], 4)
                    + pack([b & 0xF for _, b in cases], 4),
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
            self.assertEqual(raw, [value & 0xF for value in expected])
            full = program.taps["full_result"]
            actual = [
                signed_value(value, len(full))
                for value in unpack([rows[row] for row in full], lanes)
            ]
            self.assertEqual(actual, expected)

    def test_profiles_have_fixed_width_visible_rows(self):
        for name, factory in BUILDERS.items():
            with self.subTest(name=name):
                program = factory()
                outputs = [f"R{bit}" for bit in range(getattr(program, "width", 8))]
                self.assertEqual(program.outputs, {"R": outputs})
                self.assertEqual([row for row in program.rows if row.startswith("R")], outputs)
                self.assertEqual(
                    [p.rows[1] for p in program.trace[-len(outputs):]], outputs
                )

    def test_int8_mul_generates_and_reduces_all_columns_in_order(self):
        self.assert_integer_mul_column_streaming(build_int8_mul())

    def test_int4_mul_generates_and_reduces_all_columns_in_order(self):
        self.assert_integer_mul_column_streaming(build_int4_mul())

    def test_uint8_mul_generates_and_reduces_all_columns_in_order(self):
        program = build_uint8_mul()
        self.assertEqual(program.outputs, {"R": [f"R{bit}" for bit in range(8)]})
        self.assertEqual(len(program.taps["full_result"]), 16)
        self.assertEqual(program.carry_beyond_output, [])
        self.assert_integer_mul_column_streaming(program)

    def test_uint4_mul_generates_and_reduces_all_columns_in_order(self):
        program = build_uint4_mul()
        self.assertEqual(program.outputs, {"R": [f"R{bit}" for bit in range(4)]})
        self.assertEqual(len(program.taps["full_result"]), 8)
        self.assertEqual(program.carry_beyond_output, [])
        self.assert_integer_mul_column_streaming(program)

    def assert_integer_mul_column_streaming(self, program):
        width = program.width
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
                self.assertIn(stage, (f"column_{width}", f"column_{2 * width - 1}"))
        self.assertEqual(columns, sorted(columns))
        # The final unsigned column contains only the preceding carry, so it
        # emits no arithmetic primitive and remains an internal result bit.
        self.assertEqual(
            set(columns), set(range(2 * width if program.signed else 2 * width - 1))
        )
        self.assertEqual(
            sorted(products), [(i, j) for i in range(width) for j in range(width)]
        )
        self.assertEqual(sorted(program.complemented_partial_products),
                         [[i, j] for i in range(width) for j in range(width)
                          if program.signed and (i == width - 1) != (j == width - 1)])
        self.assertEqual(
            [column["bit"] for column in program.columns], list(range(2 * width))
        )
        self.assertEqual(len(program.taps["full_result"]), 2 * width)
        if not program.signed:
            self.assertEqual(program.columns[2 * width - 1], {
                "bit": 2 * width - 1, "input_bits_including_carries": 1,
                "three_input_adders": 0, "two_input_adders_using_zero": 0,
            })
        self.assertEqual(
            sum(p.op == "5RA" for p in program.trace),
            width * (width - 1) + int(program.signed),
        )

    def test_discarded_high_bit_corruption_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in (
                "uint4-add", "uint4-mul", "int4-add", "int4-mul",
                "uint8-add", "uint8-mul", "int8-add", "int8-mul",
            ):
                with self.subTest(name=name):
                    program = BUILDERS[name]()
                    # Corrupt only a non-exported bit; low-width checks still pass.
                    program.trace.insert(
                        -len(program.outputs["R"]),
                        Primitive("NOT", (program.taps["full_result"][-1],)),
                    )
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
                width = getattr(program, "width", 8)
                self.assertEqual(report["pairs"], (1 << width) ** 2)
                self.assertEqual(report["reference_mismatches"], 0)
                if name.startswith(("uint", "int")):
                    self.assertEqual(report["internal_reference_mismatches"], 0)
                    self.assertEqual(report[f"visible_low{width}_mismatches"], 0)
                    self.assertEqual(
                        report["internal_result_width"],
                        width + 1 if name.endswith("add") else 2 * width,
                    )

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
