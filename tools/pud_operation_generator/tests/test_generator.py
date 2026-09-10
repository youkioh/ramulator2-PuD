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
from pud_operation_generator.core import execute, pack, signed_value, unpack
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
        self.assertEqual(len(build_int8_add().trace), 55)
        self.assertEqual(len(build_int8_mul().trace), 628)
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
        cases = [(-128, -1), (-7, 13), (0, 127), (127, 127)]
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
            actual = [signed_value(value, len(program.outputs["R"])) for value in raw]
            self.assertEqual(actual, expected)

    def test_all_profiles_exhaustively_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name, builder in BUILDERS.items():
                program = builder()
                path, info = write_program(name, program, output)
                report = verify(name, program, path, info)
                self.assertEqual(report["pairs"], 65_536)
                self.assertEqual(report["reference_mismatches"], 0)

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
