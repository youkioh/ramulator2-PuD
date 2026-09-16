"""Focused requirements and caller-selected temporary-row integration checks."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import sys

PACKAGE_PARENT = Path(__file__).resolve().parents[2]
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from pud_operation_generator import (
    PhysicalLoweredProgram, PhysicalLoweringError, lower_to_physical,
    make_default_physical_layout, execute_physical,
)
from pud_operation_generator.core import execute
from pud_operation_generator.requirements import BUILDERS, operation_requirements, write_requirements
from pud_operation_generator.validation import validate_physical_lowering


class RequirementsTests(unittest.TestCase):
    def test_six_profiles_exact_rows_replay_and_requirements(self):
        requirements = operation_requirements()
        self.assertEqual(set(requirements), set(BUILDERS))
        for name, factory in BUILDERS.items():
            with self.subTest(profile=name):
                b = factory()
                default = lower_to_physical(b, make_default_physical_layout(b))
                count = requirements[name]["additional_temporary_rows"]
                chosen = tuple(range(900, 900 + 2*count, 2))
                layout = replace(make_default_physical_layout(b), temporary_rows=chosen)
                p = lower_to_physical(b, layout)
                designated = set(layout.inputs.values()) | set(layout.constants.values()) | set(layout.outputs.values())
                self.assertEqual(set(p.bindings.values()) - designated, set(chosen))
                self.assertEqual(p.metrics, default.metrics)
                self.assertEqual(len(p.primitives), requirements[name]["primitive_count"])
                self.assertEqual(requirements[name]["input_rows"], 16)
                self.assertEqual(requirements[name]["output_rows"], 8)
                validate_physical_lowering(b, p)
                self.assertEqual(PhysicalLoweredProgram.from_dict(p.to_dict()), p)
                initial = {row: ((0x39 if i < 8 else 0x42) >> (i % 8)) & 1
                           for i, row in enumerate(b.inputs)}
                initial.update(b.constants)
                symbolic = execute(b.trace, initial, 1)
                physical = execute_physical(p, {p.bindings[k]: v for k, v in initial.items()}, 1)
                self.assertEqual([physical[row] for row in layout.outputs.values()],
                                 [symbolic[row] for row in b.outputs["R"]])
                for wrong_count in (chosen[:-1], chosen + (999,)):
                    with self.subTest(selected_count=len(wrong_count)), self.assertRaisesRegex(
                        PhysicalLoweringError, f"exactly {count}"
                    ):
                        lower_to_physical(b, replace(layout, temporary_rows=wrong_count))

    def test_bad_explicit_rows_are_rejected(self):
        b = BUILDERS["int8-add"]()
        layout = make_default_physical_layout(b)
        for rows in ((900,)*6, (0,901,902,903,904,905), (-1,), (1024,), (True,), ("900",)):
            with self.subTest(rows=rows), self.assertRaises(PhysicalLoweringError):
                lower_to_physical(b, replace(layout, temporary_rows=rows))

    def test_generated_header_matches_json_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            document = write_requirements(path)
            first = {p.name: p.read_bytes() for p in path.iterdir()}
            self.assertEqual(json.loads(first["pud_operation_requirements.json"]), document)
            header = first["pud_operation_requirements.h"].decode()
            for name, info in document["profiles"].items():
                key = name.upper().replace("-", "_")
                self.assertIn(f"#define PUD_{key}_TMP_ROWS {info['additional_temporary_rows']}\n", header)
            write_requirements(path)
            self.assertEqual(first, {p.name: p.read_bytes() for p in path.iterdir()})
