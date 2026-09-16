"""Focused tests for local physical-row lowering."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from pud_operation_generator.__main__ import BUILDERS
from pud_operation_generator.core import Builder, Primitive, execute, pack, signed_value, unpack
from pud_operation_generator.lowering import (
    LoweredPrimitive,
    PhysicalLoweredProgram,
    PhysicalRowLayout,
    PhysicalLoweringError,
    allocate_physical_rows,
    analyze_physical_lowering,
    maximum_interval_depth,
    lower_to_physical,
    make_default_physical_layout,
    primitive_effects,
)
from pud_operation_generator.physical_replay import (
    execute_physical,
    extract_physical_results,
)
from pud_operation_generator.artifacts import (
    physical_layout_record,
    write_physical_program,
    write_program,
)
from pud_operation_generator.validation import validate_physical_lowering, verify


BASELINES = {
    "uint8-add": (41, 13, 4, 26, 30),
    "uint8-mul": (592, 26, 10, 33, 43),
    "int8-add": (46, 14, 6, 25, 31),
    "int8-mul": (612, 26, 18, 26, 44),
    "fp8-e5m2-add": (1045, 25, 17, 26, 43),
    "fp8-e5m2-mul": (326, 15, 7, 26, 33),
    "fp8-e4m3-add": (1331, 30, 22, 26, 48),
    "fp8-e4m3-mul": (318, 20, 12, 26, 38),
}


def interval_depth(intervals):
    if not intervals:
        return 0
    points = {point for item in intervals for point in (item.first_required, item.last_required)}
    return max(
        sum(item.first_required <= point <= item.last_required for item in intervals)
        for point in points
    )


def synthetic(trace, outputs=(), *, inputs=("A",), constants=None):
    builder = Builder(list(inputs))
    builder.constants = {} if constants is None else dict(constants)
    builder.outputs = {"R": list(outputs)} if outputs else {}
    builder.trace = list(trace)
    return builder


def dense_layout(builder, capacity=1024, *, reverse=False):
    protected = list(builder.inputs) + list(builder.constants)
    outputs = [name for group in builder.outputs.values() for name in group]
    input_items = list(zip(builder.inputs, range(len(builder.inputs))))
    constant_items = list(
        zip(builder.constants, range(len(builder.inputs), len(protected)))
    )
    output_items = list(
        zip(outputs, range(len(protected), len(protected) + len(outputs)))
    )
    if reverse:
        input_items.reverse()
        constant_items.reverse()
        output_items.reverse()
    return PhysicalRowLayout(
        capacity, dict(input_items), dict(constant_items), dict(output_items)
    )


def layout_record(builder, capacity=1024):
    layout = dense_layout(builder, capacity)
    return {
        "local_row_count": layout.local_row_count,
        "inputs": dict(layout.inputs),
        "constants": dict(layout.constants),
        "outputs": dict(layout.outputs),
    }


class AnalysisTests(unittest.TestCase):
    def test_all_profiles_are_derived_without_mutation(self):
        for name, factory in BUILDERS.items():
            with self.subTest(name=name):
                builder = factory()
                original_trace = deepcopy(builder.trace)
                normalized = analyze_physical_lowering(builder)
                retained, depth, _, _, _ = BASELINES[name]
                self.assertEqual(len(normalized.retained_primitives), retained)
                self.assertEqual(interval_depth(normalized.work_intervals), depth)
                self.assertEqual(builder.trace, original_trace)
                self.assertEqual(
                    normalized.output_to_final_producer,
                    tuple(
                        (output, builder.trace[retained + index].rows[0])
                        for index, output in enumerate(builder.outputs["R"])
                    ),
                )
                self.assertEqual(
                    normalized.protected_identities,
                    tuple(builder.inputs) + tuple(builder.constants),
                )
                self.assertEqual(
                    normalized.retained_original_indices, tuple(range(retained))
                )
                for index, (primitive, effect) in enumerate(
                    zip(normalized.retained_primitives, normalized.effects)
                ):
                    self.assertEqual(effect, primitive_effects(primitive, index))

    def test_effects_match_five_primitive_contracts(self):
        cases = [
            (Primitive("RowCopy", ("a", "b", "c")), ("a",), ("b", "c")),
            (Primitive("NOT", ("a",)), ("a",), ("a",)),
            (Primitive("NOT_COPY", ("a", "b", "c")), ("a",), ("a", "b", "c")),
            (Primitive("TRA", ("a", "b", "c")), ("a", "b", "c"), ("a", "b", "c")),
            (Primitive("5RA", ("a", "b", "c", "d", "e")), ("a", "b", "c", "d", "e"), ("a", "b", "c", "d", "e")),
        ]
        for primitive, reads, writes in cases:
            effect = primitive_effects(primitive)
            self.assertEqual(effect.reads, reads)
            self.assertEqual(effect.writes, writes)

    def test_interval_edges_destructive_and_extended_output(self):
        builder = synthetic(
            [
                Primitive("RowCopy", ("A", "early"), "make early"),
                Primitive("RowCopy", ("A", "result"), "make result"),
                Primitive("NOT", ("early",), "destructive"),
                Primitive("RowCopy", ("result", "R0"), "export"),
            ],
            ("R0",),
        )
        normalized = analyze_physical_lowering(builder)
        intervals = {item.symbolic_name: item for item in normalized.work_intervals}
        self.assertEqual((intervals["early"].first_required, intervals["early"].last_required), (0, 2))
        self.assertEqual((intervals["result"].first_required, intervals["result"].last_required), (1, 3))
        self.assertEqual(normalized.completion_point, 3)

    def test_shared_endpoint_counts_as_overlap(self):
        builder = synthetic(
            [
                Primitive("RowCopy", ("A", "old")),
                Primitive("RowCopy", ("old", "new")),
            ]
        )
        normalized = analyze_physical_lowering(builder)
        intervals = {item.symbolic_name: item for item in normalized.work_intervals}
        self.assertEqual(intervals["old"].last_required, intervals["new"].first_required)
        self.assertEqual(interval_depth(normalized.work_intervals), 2)

    def test_no_output_and_empty_trace(self):
        normalized = analyze_physical_lowering(synthetic([]))
        self.assertEqual(normalized.retained_primitives, ())
        self.assertEqual(normalized.removed_exports, ())
        self.assertEqual(normalized.work_intervals, ())
        self.assertEqual(normalized.protected_intervals[0].last_required, 0)
        nonempty = analyze_physical_lowering(
            synthetic([Primitive("RowCopy", ("A", "tmp"))])
        )
        self.assertEqual(len(nonempty.retained_primitives), 1)

    def test_malformed_structure_and_export_patterns_rejected(self):
        cases = {
            "arity": synthetic([Primitive("NOT", ("A", "x"))]),
            "aliased roles": synthetic([Primitive("RowCopy", ("A", "A"))]),
            "read before write": synthetic([Primitive("NOT", ("x",))]),
            "protected overwrite": synthetic([Primitive("NOT", ("A",))]),
            "nonterminal output": synthetic(
                [Primitive("RowCopy", ("A", "R0")), Primitive("RowCopy", ("A", "x"))],
                ("R0",),
            ),
            "missing export": synthetic([Primitive("RowCopy", ("A", "x"))], ("R0",)),
            "multi destination": synthetic([Primitive("RowCopy", ("A", "R0", "x"))], ("R0",)),
            "wrong order": synthetic(
                [Primitive("RowCopy", ("A", "R1")), Primitive("RowCopy", ("A", "R0"))],
                ("R0", "R1"),
            ),
            "output read": synthetic(
                [Primitive("RowCopy", ("A", "R0")), Primitive("RowCopy", ("R0", "R1"))],
                ("R0", "R1"),
            ),
            "duplicate producer": synthetic(
                [
                    Primitive("RowCopy", ("A", "x")),
                    Primitive("RowCopy", ("x", "R0")),
                    Primitive("RowCopy", ("x", "R1")),
                ],
                ("R0", "R1"),
            ),
            "protected producer": synthetic([Primitive("RowCopy", ("A", "R0"))], ("R0",)),
            "undefined producer": synthetic([Primitive("RowCopy", ("x", "R0"))], ("R0",)),
        }
        duplicate_output = synthetic(
            [Primitive("RowCopy", ("A", "x")), Primitive("RowCopy", ("x", "R0")), Primitive("RowCopy", ("x", "R0"))]
        )
        duplicate_output.outputs = {"R": ["R0", "R0"]}
        cases["duplicate output"] = duplicate_output
        for label, builder in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(PhysicalLoweringError):
                    analyze_physical_lowering(builder)


class AllocationTests(unittest.TestCase):
    def test_int8_discarded_bits_are_not_live_outs_and_rows_are_reused(self):
        for name in ("int8-add", "int8-mul"):
            with self.subTest(name=name):
                builder = BUILDERS[name]()
                normalized = analyze_physical_lowering(builder)
                lowered = lower_to_physical(builder, make_default_physical_layout(builder))
                intervals = {item.symbolic_name: item for item in normalized.work_intervals}
                self.assertEqual(list(dict(lowered.designated_outputs)), [f"R{bit}" for bit in range(8)])
                self.assertEqual(len(lowered.removed_exports), 8)
                self.assertEqual(
                    [item.final_producer for item in lowered.result_bindings],
                    builder.taps["full_result"][:8],
                )
                for bit, row in enumerate(builder.taps["full_result"][8:], 8):
                    interval = intervals[row]
                    self.assertEqual(interval.last_required, max(
                        index for index, primitive in enumerate(normalized.retained_primitives)
                        if row in primitive.rows
                    ))
                    self.assertLess(interval.last_required, normalized.completion_point)
                    if name == "int8-mul" and bit < 15:
                        self.assertTrue(any(
                            later.first_required > interval.last_required
                            and lowered.bindings[later.symbolic_name] == lowered.bindings[row]
                            for later in normalized.work_intervals
                        ), f"product bit {bit} row must actually be reused")

    def test_all_profile_metrics_are_optimal_and_deterministic(self):
        for name, factory in BUILDERS.items():
            with self.subTest(name=name):
                builder = factory()
                normalized = analyze_physical_lowering(builder)
                first = allocate_physical_rows(normalized, dense_layout(builder))
                second = allocate_physical_rows(builder, dense_layout(builder, reverse=True))
                retained, colors, temporary, designated, footprint = BASELINES[name]
                self.assertEqual(len(normalized.retained_primitives), retained)
                self.assertEqual(maximum_interval_depth(normalized.work_intervals), colors)
                self.assertEqual(first.identity_bindings, second.identity_bindings)
                self.assertEqual(first.color_to_local_row, second.color_to_local_row)
                self.assertEqual(first.additional_temporary_rows, colors - len(normalized.outputs))
                self.assertEqual(
                    (
                        first.additional_temporary_rows,
                        first.designated_rows,
                        first.physical_footprint_rows,
                        first.peak_live_identities,
                    ),
                    (temporary, designated, footprint, footprint),
                )

    def test_closed_endpoints_and_next_command_reuse(self):
        builder = synthetic(
            [
                Primitive("RowCopy", ("A", "old")),
                Primitive("RowCopy", ("old", "same_point")),
                Primitive("RowCopy", ("A", "later")),
            ]
        )
        allocation = allocate_physical_rows(builder, dense_layout(builder, 3))
        bindings = allocation.bindings
        self.assertNotEqual(bindings["old"], bindings["same_point"])
        self.assertIn(bindings["later"], {bindings["old"], bindings["same_point"]})

    def test_output_row_hosts_only_an_earlier_temporary(self):
        builder = synthetic(
            [
                Primitive("RowCopy", ("A", "early")),
                Primitive("NOT", ("early",)),
                Primitive("RowCopy", ("A", "result")),
                Primitive("NOT", ("result",)),
                Primitive("RowCopy", ("result", "R0")),
            ],
            ("R0",),
        )
        layout = PhysicalRowLayout(3, {"A": 0}, {}, {"R0": 1})
        allocation = allocate_physical_rows(builder, layout)
        self.assertEqual(allocation.bindings["early"], 1)
        self.assertEqual(allocation.bindings["result"], 1)
        normalized = allocation.normalized
        intervals = {item.symbolic_name: item for item in normalized.work_intervals}
        self.assertLess(intervals["early"].last_required, intervals["result"].first_required)

    def test_no_output_and_exact_capacity(self):
        builder = synthetic(
            [
                Primitive("RowCopy", ("A", "x")),
                Primitive("RowCopy", ("x", "y")),
            ]
        )
        allocation = allocate_physical_rows(builder, dense_layout(builder, 3))
        self.assertEqual(allocation.additional_temporary_rows, 2)
        self.assertEqual(allocation.designated_rows, 1)
        self.assertEqual(allocation.physical_footprint_rows, 3)
        empty = synthetic([])
        empty_allocation = allocate_physical_rows(empty, dense_layout(empty, 1))
        self.assertEqual(empty_allocation.additional_temporary_rows, 0)
        self.assertEqual(empty_allocation.physical_footprint_rows, 1)

    def test_layout_rejections_and_capacity_failure(self):
        builder = synthetic(
            [Primitive("RowCopy", ("A", "x")), Primitive("RowCopy", ("x", "R0"))],
            ("R0",),
            constants={"C": 0},
        )
        invalid = [
            PhysicalRowLayout(0, {"A": 0}, {"C": 1}, {"R0": 2}),
            PhysicalRowLayout(4, {}, {"C": 1}, {"R0": 2}),
            PhysicalRowLayout(4, {"A": 0, "x": 3}, {"C": 1}, {"R0": 2}),
            PhysicalRowLayout(4, {"A": 0}, {"C": 1}, {"R0": 2, "R1": 3}),
            PhysicalRowLayout(4, {"A": True}, {"C": 1}, {"R0": 2}),
            PhysicalRowLayout(4, {"A": 4}, {"C": 1}, {"R0": 2}),
            PhysicalRowLayout(4, {"A": 0}, {"C": 0}, {"R0": 2}),
            PhysicalRowLayout(4, {"A": 0}, {"C": 1}, {"R0": 0}),
            PhysicalRowLayout(4, {"A": 0}, {"C": 1}, {"R0": 2}, {"x": 3}),
        ]
        for layout in invalid:
            with self.subTest(layout=layout):
                with self.assertRaises(PhysicalLoweringError):
                    allocate_physical_rows(builder, layout)

        two_outputs = synthetic(
            [
                Primitive("RowCopy", ("A", "x")),
                Primitive("RowCopy", ("A", "y")),
                Primitive("RowCopy", ("x", "R0")),
                Primitive("RowCopy", ("y", "R1")),
            ],
            ("R0", "R1"),
        )
        with self.assertRaises(PhysicalLoweringError):
            allocate_physical_rows(
                two_outputs, PhysicalRowLayout(4, {"A": 0}, {}, {"R0": 1, "R1": 1})
            )

        needs_temporary = synthetic(
            [
                Primitive("RowCopy", ("A", "x")),
                Primitive("RowCopy", ("A", "y")),
                Primitive("RowCopy", ("x", "R0")),
            ],
            ("R0",),
        )
        with self.assertRaisesRegex(PhysicalLoweringError, "insufficient"):
            allocate_physical_rows(
                needs_temporary, PhysicalRowLayout(2, {"A": 0}, {}, {"R0": 1})
            )


class LoweredTraceTests(unittest.TestCase):
    def test_all_profiles_preserve_exact_retained_sequence_and_provenance(self):
        for name, factory in BUILDERS.items():
            with self.subTest(name=name):
                builder = factory()
                original = deepcopy(builder.trace)
                lowered = lower_to_physical(builder, dense_layout(builder))
                retained = original[: len(original) - len(builder.outputs["R"])]
                self.assertEqual(len(lowered.primitives), len(retained))
                for index, (physical, symbolic) in enumerate(
                    zip(lowered.primitives, retained)
                ):
                    self.assertEqual(
                        (physical.opcode, physical.symbolic_rows, physical.original_index, physical.stage),
                        (symbolic.op, symbolic.rows, index, symbolic.stage),
                    )
                    self.assertEqual(
                        physical.physical_rows,
                        tuple(lowered.bindings[row] for row in symbolic.rows),
                    )
                    self.assertTrue(all(type(row) is int for row in physical.physical_rows))
                self.assertEqual(builder.trace, original)
                self.assertEqual(
                    [item.original_index for item in lowered.removed_exports],
                    list(range(len(retained), len(original))),
                )
                for result in lowered.result_bindings:
                    self.assertEqual(
                        lowered.bindings[result.final_producer], result.physical_row
                    )
                    self.assertEqual(
                        dict(lowered.designated_outputs)[result.output_name],
                        result.physical_row,
                    )
                    self.assertNotIn(result.output_name, lowered.bindings)

    def test_artifact_ready_dictionary_round_trip_is_lossless(self):
        builder = BUILDERS["int8-add"]()
        lowered = lower_to_physical(builder, dense_layout(builder))
        encoded = json.loads(json.dumps(lowered.to_dict()))
        self.assertEqual(PhysicalLoweredProgram.from_dict(encoded), lowered)
        self.assertEqual(encoded["schema_version"], 2)
        self.assertEqual(set(encoded["allocation_metrics"]), {
            "additional_temporary_rows", "designated_rows",
            "physical_footprint_rows", "peak_live_identities",
        })
        self.assertEqual(encoded["allocation_metrics"]["additional_temporary_rows"], 6)
        with self.assertRaisesRegex(PhysicalLoweringError, "unsupported.*schema"):
            PhysicalLoweredProgram.from_dict({**encoded, "schema_version": 1})
        self.assertEqual(
            [item.original_index for item in lowered.primitives],
            list(range(len(lowered.primitives))),
        )

    def test_lowered_representation_is_local_row_only(self):
        builder = BUILDERS["fp8-e5m2-mul"]()
        lowered = lower_to_physical(builder, dense_layout(builder))
        serialized = json.dumps(lowered.to_dict())
        for forbidden in ("Bank", "subarray", "CellID", "MatRange", "request", "timing", "phase"):
            self.assertNotIn(forbidden, serialized)


def replay_fixture(primitives, *, protected=()):
    return PhysicalLoweredProgram(
        primitives=tuple(
            LoweredPrimitive(opcode, tuple(rows), tuple(f"s{i}" for i in range(len(rows))), index, "test")
            for index, (opcode, rows) in enumerate(primitives)
        ),
        identity_bindings=(),
        designated_inputs=tuple((f"P{index}", row) for index, row in enumerate(protected)),
        designated_constants=(),
        designated_outputs=(),
        result_bindings=(),
        removed_exports=(),
        local_row_count=16,
        additional_temporary_rows=0,
        designated_rows=len(protected),
        physical_footprint_rows=len(protected),
        peak_live_identities=len(protected),
    )


class PhysicalReplayTests(unittest.TestCase):
    def assertReplay(self, primitive, initial, expected, lanes=4):
        actual = execute_physical(replay_fixture([primitive]), initial, lanes)
        for row, value in expected.items():
            self.assertEqual(actual[row], value)

    def test_directed_primitive_snapshot_and_destructive_semantics(self):
        self.assertReplay(("RowCopy", (0, 1, 2)), {0: 0b1010}, {0: 0b1010, 1: 0b1010, 2: 0b1010})
        self.assertReplay(("NOT", (0,)), {0: 0b1010}, {0: 0b0101})
        self.assertReplay(("NOT_COPY", (0, 1, 2)), {0: 0b1010}, {0: 0b0101, 1: 0b0101, 2: 0b0101})
        self.assertReplay(("TRA", (0, 1, 2)), {0: 0b1100, 1: 0b1010, 2: 0b0110}, {0: 0b1110, 1: 0b1110, 2: 0b1110})
        self.assertReplay(("5RA", (0, 1, 2, 3, 4)), {0: 0b1111, 1: 0b1100, 2: 0b1010, 3: 0b0110, 4: 0}, {0: 0b1110, 1: 0b1110, 2: 0b1110, 3: 0b1110, 4: 0b1110})

    def test_initialization_lane_and_alias_errors(self):
        with self.assertRaisesRegex(PhysicalLoweringError, "uninitialized"):
            execute_physical(replay_fixture([("NOT", (2,))]), {}, 4)
        with self.assertRaisesRegex(PhysicalLoweringError, "fit within"):
            execute_physical(replay_fixture([]), {0: 0b10000}, 4)
        for opcode, rows in (
            ("RowCopy", (0, 0)),
            ("NOT_COPY", (0, 1, 1)),
            ("TRA", (0, 1, 0)),
            ("5RA", (0, 1, 2, 3, 0)),
        ):
            with self.subTest(opcode=opcode):
                with self.assertRaisesRegex(PhysicalLoweringError, "pairwise distinct"):
                    execute_physical(
                        replay_fixture([(opcode, rows)]),
                        {row: 0 for row in set(rows)},
                        4,
                    )

    def test_protected_rows_are_checked_at_exit(self):
        malformed = replay_fixture([("NOT", (0,))], protected=(0,))
        with self.assertRaisesRegex(PhysicalLoweringError, "protected physical rows changed"):
            execute_physical(malformed, {0: 0}, 1)

    def test_reused_temporary_row_executes_correctly(self):
        builder = synthetic(
            [
                Primitive("RowCopy", ("A", "early")),
                Primitive("NOT", ("early",)),
                Primitive("RowCopy", ("A", "result")),
                Primitive("NOT", ("result",)),
                Primitive("RowCopy", ("result", "R0")),
            ],
            ("R0",),
        )
        lowered = lower_to_physical(
            builder, PhysicalRowLayout(2, {"A": 0}, {}, {"R0": 1})
        )
        final = execute_physical(lowered, {0: 0b1010}, 4)
        self.assertEqual(extract_physical_results(lowered, final), {"R0": 0b0101})

    def test_selected_integer_and_fp8_match_symbolic_rows(self):
        cases = [(0, 0), (1, 255), (127, 129), (255, 255)]
        for name in ("uint8-add", "fp8-e4m3-mul"):
            with self.subTest(name=name):
                builder = BUILDERS[name]()
                lowered = lower_to_physical(builder, dense_layout(builder))
                lanes = len(cases)
                initial = dict(
                    zip(
                        builder.inputs,
                        pack([a for a, _ in cases], 8)
                        + pack([b for _, b in cases], 8),
                    )
                )
                initial.update(
                    {
                        row: (1 << lanes) - 1 if value else 0
                        for row, value in builder.constants.items()
                    }
                )
                symbolic = execute(builder.trace, initial, lanes)
                physical_initial = {
                    lowered.bindings[name]: value for name, value in initial.items()
                }
                physical = execute_physical(lowered, physical_initial, lanes)
                results = extract_physical_results(lowered, physical)
                self.assertEqual(
                    [results[name] for name in builder.outputs["R"]],
                    [symbolic[name] for name in builder.outputs["R"]],
                )
                for symbolic_name, value in initial.items():
                    self.assertEqual(physical[lowered.bindings[symbolic_name]], value)

    def test_symbolically_distinct_but_physically_aliased_trace_fails(self):
        builder = BUILDERS["uint8-add"]()
        lowered = lower_to_physical(builder, dense_layout(builder))
        first = lowered.primitives[0]
        malformed_primitive = replace(
            first,
            physical_rows=(first.physical_rows[0],) * len(first.physical_rows),
        )
        malformed = replace(
            lowered, primitives=(malformed_primitive,) + lowered.primitives[1:]
        )
        initial = {
            **{row: 0 for row in dict(lowered.designated_inputs).values()},
            **{row: 0 for row in dict(lowered.designated_constants).values()},
        }
        with self.assertRaisesRegex(PhysicalLoweringError, "pairwise distinct"):
            execute_physical(malformed, initial, 1)


class PhysicalValidationTests(unittest.TestCase):
    def test_int8_full_results_exhaustively_observed_before_row_reuse(self):
        left = [value for value in range(256) for _ in range(256)]
        right = list(range(256)) * 256
        lanes = len(left)
        for name in ("int8-add", "int8-mul"):
            with self.subTest(name=name):
                builder = BUILDERS[name]()
                normalized = analyze_physical_lowering(builder)
                lowered = lower_to_physical(builder, make_default_physical_layout(builder))
                initial = dict(zip(builder.inputs, pack(left, 8) + pack(right, 8)))
                initial.update({row: (1 << lanes) - 1 if value else 0
                                for row, value in builder.constants.items()})
                physical_initial = {lowered.bindings[row]: value for row, value in initial.items()}
                intervals = {item.symbolic_name: item for item in normalized.work_intervals}
                snapshots = []
                # Replay prefixes to observe each value at its final required
                # command. This test adds no primitive or allocation lifetime.
                for row in builder.taps["full_result"] + builder.carry_beyond_output:
                    end = intervals[row].last_required
                    prefix = replace(lowered, primitives=lowered.primitives[:end + 1], result_bindings=())
                    storage = execute_physical(prefix, physical_initial, lanes)
                    snapshots.append(storage[lowered.bindings[row]])
                width = len(builder.taps["full_result"])
                full = unpack(snapshots[:width], lanes)
                expected = [
                    signed_value(a, 8) + signed_value(b, 8) if name.endswith("add")
                    else signed_value(a, 8) * signed_value(b, 8)
                    for a, b in zip(left, right)
                ]
                self.assertEqual([signed_value(value, width) for value in full], expected)
                if name == "int8-mul":
                    carry = unpack(snapshots[width:], lanes)
                    self.assertEqual([value + (high << 16) for value, high in zip(full, carry)],
                                     [value + (1 << 16) for value in expected])

    def test_all_profiles_exhaustively_establish_triple_equality(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name, factory in BUILDERS.items():
                with self.subTest(name=name):
                    builder = factory()
                    path, info = write_program(name, builder, output)
                    lowered = lower_to_physical(
                        builder, make_default_physical_layout(builder)
                    )
                    report = verify(name, builder, path, info, lowered=lowered)
                    physical = report["physical_lowering"]
                    self.assertEqual(report["pairs"], 65_536)
                    self.assertEqual(report["reference_mismatches"], 0)
                    self.assertEqual(
                        physical["reference_symbolic_physical_mismatches"], 0
                    )
                    self.assertTrue(physical["input_constant_preservation"])
                    self.assertTrue(physical["output_placement"])
                    self.assertTrue(physical["exact_terminal_export_removal"])
                    self.assertTrue(physical["closed_interval_interference"])
                    self.assertTrue(physical["primitive_physical_distinctness"])
                    self.assertTrue(physical["deterministic_allocation"])
                    _, depth, temporary, designated, footprint = BASELINES[name]
                    self.assertEqual(physical["work_interval_depth"], depth)
                    self.assertEqual(
                        physical["allocation_metrics"],
                        {
                            "additional_temporary_rows": temporary,
                            "designated_rows": designated,
                            "physical_footprint_rows": footprint,
                            "peak_live_identities": footprint,
                        },
                    )

    def test_symbolic_only_report_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            builder = BUILDERS["uint8-add"]()
            path, info = write_program("uint8-add", builder, Path(directory))
            report = verify("uint8-add", builder, path, info)
            self.assertNotIn("physical_lowering", report)
            self.assertEqual(report["serialized_trace_replay_all_rows_equal"], True)

    def test_corrupted_lowering_layers_are_rejected_independently(self):
        builder = BUILDERS["uint8-add"]()
        lowered = lower_to_physical(builder, dense_layout(builder))

        first_result = lowered.result_bindings[0]
        wrong_result = replace(
            lowered,
            result_bindings=(
                replace(first_result, physical_row=(first_result.physical_row + 1) % 1024),
            )
            + lowered.result_bindings[1:],
        )
        wrong_export = replace(
            lowered,
            removed_exports=(replace(lowered.removed_exports[0], original_index=0),)
            + lowered.removed_exports[1:],
        )
        first_primitive = lowered.primitives[0]
        aliased_primitive = replace(
            lowered,
            primitives=(
                replace(
                    first_primitive,
                    physical_rows=(first_primitive.physical_rows[0],)
                    * len(first_primitive.physical_rows),
                ),
            )
            + lowered.primitives[1:],
        )
        retained_export = replace(
            lowered,
            primitives=lowered.primitives
            + (
                LoweredPrimitive(
                    "RowCopy",
                    (first_result.physical_row, first_result.physical_row + 1),
                    (first_result.final_producer, first_result.output_name),
                    lowered.removed_exports[0].original_index,
                    lowered.removed_exports[0].stage,
                ),
            ),
        )
        inconsistent_metrics = replace(
            lowered, additional_temporary_rows=lowered.additional_temporary_rows + 1
        )

        normalized = analyze_physical_lowering(builder)
        overlapping = next(
            (left, right)
            for index, left in enumerate(normalized.work_intervals)
            for right in normalized.work_intervals[index + 1 :]
            if left.first_required <= right.last_required
            and right.first_required <= left.last_required
        )
        corrupted_bindings = lowered.bindings
        corrupted_bindings[overlapping[1].symbolic_name] = corrupted_bindings[
            overlapping[0].symbolic_name
        ]
        overlapping_binding = replace(
            lowered,
            identity_bindings=tuple(sorted(corrupted_bindings.items())),
            primitives=tuple(
                replace(
                    primitive,
                    physical_rows=tuple(
                        corrupted_bindings[name] for name in primitive.symbolic_rows
                    ),
                )
                for primitive in lowered.primitives
            ),
        )

        cases = {
            "wrong result binding": wrong_result,
            "misidentified export": wrong_export,
            "aliased primitive": aliased_primitive,
            "retained export": retained_export,
            "inconsistent metrics": inconsistent_metrics,
            "overlapping interval binding": overlapping_binding,
        }
        for label, corrupted in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(PhysicalLoweringError):
                    validate_physical_lowering(builder, corrupted)


class PhysicalSurfaceTests(unittest.TestCase):
    def run_cli(self, directory, layout_document, *names):
        root = Path(directory)
        layout_path = root / "layout.json"
        if isinstance(layout_document, str):
            layout_path.write_text(layout_document, encoding="utf-8")
        else:
            layout_path.write_text(json.dumps(layout_document), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pud_operation_generator",
                "--only",
                *names,
                "--physical-layout",
                str(layout_path),
                "--out",
                str(root / "out"),
            ],
            cwd=PACKAGE_PARENT,
            text=True,
            capture_output=True,
        )

    def run_default_cli(self, directory, *names, physical_layout=None):
        root = Path(directory)
        command = [
            sys.executable,
            "-m",
            "pud_operation_generator",
            "--only",
            *names,
            "--use-default-physical-layout",
            "--out",
            str(root / "out"),
        ]
        if physical_layout is not None:
            command.extend(["--physical-layout", str(physical_layout)])
        return subprocess.run(
            command,
            cwd=PACKAGE_PARENT,
            text=True,
            capture_output=True,
        )

    def test_default_layout_helper_uses_only_consecutive_designations(self):
        for name, factory in BUILDERS.items():
            with self.subTest(name=name):
                builder = factory()
                layout = make_default_physical_layout(builder)
                self.assertEqual(layout, make_default_physical_layout(builder))
                self.assertEqual(
                    layout,
                    make_default_physical_layout(analyze_physical_lowering(builder)),
                )
                designated = (
                    list(layout.inputs.items())
                    + list(layout.constants.items())
                    + list(layout.outputs.items())
                )
                self.assertEqual(layout.local_row_count, 1024)
                self.assertEqual(
                    [symbol for symbol, _ in designated],
                    list(builder.inputs)
                    + list(builder.constants)
                    + list(builder.outputs["R"]),
                )
                self.assertEqual(
                    [row for _, row in designated], list(range(len(designated)))
                )
                self.assertEqual(dict(layout.work), {})
                lowered = lower_to_physical(builder, layout)
                work_names = {
                    item.symbolic_name
                    for item in analyze_physical_lowering(builder).work_intervals
                }
                self.assertEqual(
                    work_names,
                    set(lowered.bindings)
                    - set(builder.inputs)
                    - set(builder.constants),
                )

        builder = BUILDERS["uint8-add"]()
        too_small = make_default_physical_layout(builder, local_row_count=29)
        with self.assertRaisesRegex(PhysicalLoweringError, "insufficient"):
            lower_to_physical(builder, too_small)

    def test_default_cli_emits_reusable_layout_and_provenance(self):
        names = ("uint8-add", "int8-add", "int8-mul", "fp8-e5m2-mul")
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_default_cli(directory, *names)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("reference/symbolic/physical PASS", completed.stdout)
            output = Path(directory) / "out"
            layout_path = output / "default-physical-layout.json"
            self.assertIn(
                "int8-mul: 612 primitives (physical; 620 symbolic), "
                "input rows: 16, output rows: 8, temporary rows: 18,",
                completed.stdout,
            )
            self.assertNotIn("scratch", completed.stdout)
            self.assertTrue(layout_path.is_file())
            first_bytes = layout_path.read_bytes()
            document = json.loads(layout_path.read_text())
            self.assertEqual(list(document), list(names))
            for name in names:
                builder = BUILDERS[name]()
                self.assertEqual(
                    document[name],
                    physical_layout_record(make_default_physical_layout(builder)),
                )
                if name.startswith("int8-"):
                    self.assertEqual(list(document[name]["outputs"]), [f"R{bit}" for bit in range(8)])
                physical = json.loads(
                    (output / f"{name}.physical.json").read_text()
                )
                self.assertEqual(physical["layout_provenance"], "default_generated")
            report = json.loads((output / "validation.json").read_text())
            for name in names:
                self.assertEqual(
                    report["variants"][name]["validation"]["physical_lowering"][
                        "layout_provenance"
                    ],
                    "default_generated",
                )

            with tempfile.TemporaryDirectory() as repeat_directory:
                repeated = self.run_default_cli(repeat_directory, *names)
                self.assertEqual(repeated.returncode, 0, repeated.stderr)
                self.assertEqual(
                    first_bytes,
                    (
                        Path(repeat_directory)
                        / "out"
                        / "default-physical-layout.json"
                    ).read_bytes(),
                )

            with tempfile.TemporaryDirectory() as reuse_directory:
                reused = self.run_cli(reuse_directory, document, *names)
                self.assertEqual(reused.returncode, 0, reused.stderr)
                self.assertEqual(reused.stdout, completed.stdout)
                reused_output = Path(reuse_directory) / "out"
                for name in names:
                    physical = json.loads(
                        (reused_output / f"{name}.physical.json").read_text()
                    )
                    self.assertEqual(
                        physical["layout_provenance"], "caller_provided"
                    )

    def test_default_layout_takes_precedence_over_explicit_path(self):
        with tempfile.TemporaryDirectory() as directory:
            ignored = Path(directory) / "does-not-exist.json"
            completed = self.run_default_cli(
                directory, "uint8-add", physical_layout=ignored
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(
                (Path(directory) / "out" / "default-physical-layout.json").is_file()
            )

    def test_int8_cli_rejects_old_widened_output_layouts(self):
        for name, old_width in (("int8-add", 9), ("int8-mul", 16)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                record = layout_record(BUILDERS[name]())
                record["outputs"].update({f"R{bit}": 100 + bit for bit in range(8, old_width)})
                completed = self.run_cli(directory, {name: record}, name)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("R8", completed.stderr)

    def test_cli_without_layout_remains_symbolic_only(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pud_operation_generator",
                    "--only",
                    "uint8-add",
                    "--out",
                    str(output),
                ],
                cwd=PACKAGE_PARENT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("reference/replay PASS", completed.stdout)
            self.assertIn(
                "uint8-add: 50 primitives (symbolic), input rows: 16, "
                "output rows: 9, temporary rows: 4 (required for physical lowering),",
                completed.stdout,
            )
            self.assertNotIn("scratch", completed.stdout)
            self.assertFalse((output / "default-physical-layout.json").exists())
            self.assertFalse((output / "uint8-add.physical.json").exists())
            report = json.loads((output / "validation.json").read_text())
            self.assertNotIn(
                "physical_lowering",
                report["variants"]["uint8-add"]["validation"],
            )

    def test_physical_artifact_schema_and_deterministic_regeneration(self):
        builder = BUILDERS["uint8-add"]()
        lowered = lower_to_physical(builder, dense_layout(builder))
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path, artifact = write_physical_program(
                "uint8-add", lowered, Path(first)
            )
            second_path, _ = write_physical_program(
                "uint8-add", lowered, Path(second)
            )
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
            self.assertEqual(artifact["schema_version"], 2)
            self.assertEqual(artifact["kind"], "pud-physical-lowered-program")
            self.assertEqual(artifact["profile"], "uint8-add")
            self.assertEqual(len(artifact["lowered_primitives"]), 41)
            self.assertEqual(len(artifact["removed_terminal_exports"]), 9)
            self.assertEqual(artifact["allocation_metrics"]["physical_footprint_rows"], 30)
            self.assertIn("not complete canonical Ramulator addresses", artifact["local_row_scope"])
            self.assertNotIn("request_fragment", artifact)

    def test_cli_success_and_layout_failures(self):
        names = ("uint8-add", "int8-add", "int8-mul", "fp8-e5m2-mul")
        layouts = {name: layout_record(BUILDERS[name]()) for name in names}
        uint8_builder = BUILDERS["uint8-add"]()
        layouts["uint8-add"]["inputs"] = {
            name: 101 + 2 * index for index, name in enumerate(uint8_builder.inputs)
        }
        layouts["uint8-add"]["constants"] = {"CONST_ZERO": 500}
        layouts["uint8-add"]["outputs"] = {
            name: 800 + index
            for index, name in enumerate(uint8_builder.outputs["R"])
        }
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_cli(directory, layouts, *names)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("reference/symbolic/physical PASS", completed.stdout)
            output = Path(directory) / "out"
            for name in names:
                self.assertTrue((output / f"{name}.physical.json").is_file())
                self.assertTrue((output / f"{name}.primitives.txt").is_file())
                self.assertTrue((output / f"{name}.rows.json").is_file())
                self.assertTrue((output / f"{name}.requests.inc").is_file())
            report = json.loads((output / "validation.json").read_text())
            self.assertIn(
                "physical_lowering", report["variants"][names[0]]["validation"]
            )
            for name in names:
                physical = json.loads((output / f"{name}.physical.json").read_text())
                self.assertEqual(physical["layout_provenance"], "caller_provided")
                self.assertEqual(
                    physical["designated_bindings"],
                    {
                        category: layouts[name][category]
                        for category in ("inputs", "constants", "outputs")
                    },
                )
                self.assertEqual(
                    report["variants"][name]["validation"]["physical_lowering"][
                        "layout_provenance"
                    ],
                    "caller_provided",
                )

        failures = [
            ({}, "missing layout"),
            ("{", "Expecting property name"),
            (
                {
                    "uint8-add": {
                        **layout_record(BUILDERS["uint8-add"]()),
                        "work": {"t0000": 100},
                    }
                },
                "unsupported work",
            ),
            (
                {"uint8-add": layout_record(BUILDERS["uint8-add"](), 26)},
                "insufficient local-row capacity",
            ),
        ]
        for document, message in failures:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                completed = self.run_cli(directory, document, "uint8-add")
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(message, completed.stderr)
                self.assertIn("uint8-add", completed.stderr)

    def test_copied_package_supports_physical_lowering_standalone(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            copied = temporary_root / "pud_operation_generator"
            shutil.copytree(ROOT, copied, ignore=shutil.ignore_patterns("__pycache__"))
            builder = BUILDERS["int8-add"]()
            layout_path = temporary_root / "layout.json"
            layout_path.write_text(
                json.dumps({"int8-add": layout_record(builder)}), encoding="utf-8"
            )
            output = temporary_root / "out"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pud_operation_generator",
                    "--only",
                    "int8-add",
                    "--physical-layout",
                    str(layout_path),
                    "--out",
                    str(output),
                ],
                cwd=temporary_root,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("reference/symbolic/physical PASS", completed.stdout)
            self.assertTrue((output / "int8-add.physical.json").is_file())


if __name__ == "__main__":
    unittest.main()
