"""Exhaustive arithmetic references and serialized trace replay."""

from collections import Counter
import csv

from .core import execute, pack, read_program, signed_value, unpack, validate_structure
from .fp8 import (
    E4M3,
    E5M2,
    fp8_add_reference,
    normal_positive_grid,
    normal_value,
    scalar_fp8_mul_reference,
)
from .lowering import (
    PhysicalLoweredProgram,
    PhysicalLoweringError,
    PhysicalRowLayout,
    analyze_physical_lowering,
    lower_to_physical,
)
from .physical_replay import execute_physical, extract_physical_results


FORMATS = {"e5m2": E5M2, "e4m3": E4M3}


def _execute_and_replay(builder, path, info):
    width = getattr(builder, "width", 8)
    size = 1 << width
    left = [value for value in range(size) for _ in range(size)]
    right = list(range(size)) * size
    lanes = size * size
    initial = dict(zip(builder.inputs, pack(left, width) + pack(right, width)))
    initial.update(
        {
            row: (1 << lanes) - 1 if value else 0
            for row, value in info["constants"].items()
        }
    )

    rows = execute(builder.trace, initial, lanes)
    parsed = read_program(path)
    validate_structure(parsed, builder.inputs, info["constants"], builder.outputs["R"])
    assert [(item.op, item.rows) for item in parsed] == [
        (item.op, item.rows) for item in builder.trace
    ]
    assert execute(parsed, initial, lanes) == rows, "serialized replay differs"
    raw = unpack([rows[row] for row in builder.outputs["R"]], lanes)
    return left, right, lanes, rows, raw


def _verify_integer(name, builder, left, right, lanes, rows, raw, library):
    width = builder.width
    left_values = [signed_value(value, width) for value in left] if builder.signed else left
    right_values = [signed_value(value, width) for value in right] if builder.signed else right
    actual = (
        [signed_value(value, len(builder.outputs["R"])) for value in raw]
        if builder.signed
        else raw
    )
    expected = [
        a + b if name.endswith("add") else a * b
        for a, b in zip(left_values, right_values)
    ]
    assert actual == expected

    report = {"reference_mismatches": 0}
    if name == "int8-mul":
        carry = unpack([rows[row] for row in builder.carry_beyond_output], lanes)
        assert all(
            result + (high << (2 * width))
            == reference + (1 << (2 * width))
            for result, high, reference in zip(raw, carry, expected)
        )
        report["signed_correction_identity"] = True

    if library:
        import numpy as np

        dtype = np.int16 if builder.signed else np.uint16
        a = np.asarray(left_values, dtype=dtype)
        b = np.asarray(right_values, dtype=dtype)
        reference = a + b if name.endswith("add") else a * b
        assert np.array_equal(actual, reference)
        report["numpy_mismatches"] = 0
    return report


def _unpack_tap(rows, builder, name, lanes, signed_width=0):
    values = unpack([rows[row] for row in builder.taps[name]], lanes)
    if signed_width:
        return [signed_value(value, signed_width) for value in values]
    return values


def _verify_fp8_add(name, builder, format_, path, left, right, lanes, rows, raw):
    references = [
        fp8_add_reference(a, b, format_) for a, b in zip(left, right)
    ]
    aligned_width = format_.fraction_bits + 2
    tap_fields = {
        "exponent_difference_signed": ("difference", format_.exponent_bits + 1),
        "aligned_left": ("aligned_left", 0),
        "aligned_right": ("aligned_right", 0),
        "common_exponent": ("common_exponent", 0),
        "signed_left": ("signed_left", aligned_width + 1),
        "signed_right": ("signed_right", aligned_width + 1),
        "signed_sum": ("signed_sum", aligned_width + 1),
        "result_sign": ("result_sign", 0),
        "magnitude": ("magnitude", 0),
        "fraction": ("fraction", 0),
        "exponent_signed": ("exponent", format_.exponent_bits + 2),
    }
    for tap, (field, signed_width) in tap_fields.items():
        values = _unpack_tap(rows, builder, tap, lanes, signed_width)
        assert values == [reference[field] for reference in references], tap

    for field in ("branch", "normalization"):
        for value in {reference[field] for reference in references}:
            values = _unpack_tap(rows, builder, value, lanes)
            assert values == [
                int(reference[field] == value) for reference in references
            ]

    assert all(
        result == reference["encoding"]
        for result, reference in zip(raw, references)
        if reference["fields_fit"]
    )
    domain = [reference["comparison_domain"] for reference in references]

    with (path.parent / f"{name}-domain-counts.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["input_category", "result_category", "pairs"])
        categories = Counter(
            (
                "both_normal"
                if format_.is_normal(a) and format_.is_normal(b)
                else "non_normal_input",
                "cancellation"
                if reference["magnitude"] == 0
                else "normal_result"
                if reference["comparison_domain"]
                else "outside_comparison_domain",
            )
            for a, b, reference in zip(left, right, references)
        )
        for (inputs, result), count in sorted(categories.items()):
            writer.writerow([inputs, result, count])

    report = {
        "reference_mismatches": 0,
        "intermediate_and_predicate_checks": True,
        "fields_fit_pairs": sum(reference["fields_fit"] for reference in references),
        "undefined_encoding_pairs": sum(
            not reference["fields_fit"] for reference in references
        ),
        "numeric_comparison_domain_pairs": sum(domain),
        "alignment_branch_coverage": dict(
            Counter(reference["branch"] for reference in references)
        ),
        "normalization_branch_coverage": dict(
            Counter(reference["normalization"] for reference in references)
        ),
    }
    return report, domain


def _verify_fp8_mul(builder, format_, left, right, raw):
    assert raw == [
        scalar_fp8_mul_reference(a, b, format_) for a, b in zip(left, right)
    ]
    grid = normal_positive_grid(format_)
    domain = []
    for a, b, result in zip(left, right, raw):
        normal = format_.is_normal(a) and format_.is_normal(b)
        exact = normal_value(a, format_) * normal_value(b, format_) if normal else 0
        magnitude = abs(exact)
        allowed = normal and format_.min_normal <= magnitude <= format_.max_normal
        domain.append(allowed)
        if allowed:
            encoded = max(code for value, code in grid if value <= magnitude)
            assert result == (encoded | (0x80 if exact < 0 else 0))
    return {
        "reference_mismatches": 0,
        "exact_rational_domain_mismatches": 0,
        "numeric_comparison_domain_pairs": sum(domain),
    }, domain


def _add_library_comparison(name, format_, left, right, raw, domain, report):
    import ml_dtypes
    import numpy as np

    dtype = (
        ml_dtypes.float8_e4m3fn
        if format_.name == "e4m3"
        else ml_dtypes.float8_e5m2
    )
    a = np.asarray(left, dtype=np.uint8).view(dtype)
    b = np.asarray(right, dtype=np.uint8).view(dtype)
    with np.errstate(all="ignore"):
        reference = (
            np.add(a, b) if name.endswith("add") else np.multiply(a, b)
        ).view(np.uint8).tolist()
    report["library_domain_bit_differences"] = sum(
        actual != expected
        for actual, expected, allowed in zip(raw, reference, domain)
        if allowed
    )
    report["library_all_encoding_bit_differences_diagnostic_only"] = sum(
        actual != expected for actual, expected in zip(raw, reference)
    )


def _independent_closed_interval_depth(intervals):
    if not intervals:
        return 0
    points = sorted(
        {point for item in intervals for point in (item.first_required, item.last_required)}
    )
    return max(
        sum(item.first_required <= point <= item.last_required for item in intervals)
        for point in points
    )


def validate_physical_lowering(builder, lowered):
    """Independently validate a complete local-row lowering artifact."""

    if not isinstance(lowered, PhysicalLoweredProgram):
        raise PhysicalLoweringError("physical validation requires a PhysicalLoweredProgram")
    normalized = analyze_physical_lowering(builder)
    bindings = dict(lowered.identity_bindings)
    if len(bindings) != len(lowered.identity_bindings):
        raise PhysicalLoweringError("duplicate symbolic identity binding")
    expected_identities = set(normalized.protected_identities) | {
        item.symbolic_name for item in normalized.work_intervals
    }
    if set(bindings) != expected_identities:
        raise PhysicalLoweringError("physical identity bindings do not exactly cover retained identities")
    if any(
        isinstance(row, bool)
        or not isinstance(row, int)
        or not 0 <= row < lowered.local_row_count
        for row in bindings.values()
    ):
        raise PhysicalLoweringError("physical identity binding is not an in-range integer row")

    designated_inputs = dict(lowered.designated_inputs)
    designated_constants = dict(lowered.designated_constants)
    designated_outputs = dict(lowered.designated_outputs)
    if len(designated_inputs) != len(lowered.designated_inputs):
        raise PhysicalLoweringError("duplicate designated input binding")
    if len(designated_constants) != len(lowered.designated_constants):
        raise PhysicalLoweringError("duplicate designated constant binding")
    if len(designated_outputs) != len(lowered.designated_outputs):
        raise PhysicalLoweringError("duplicate designated output binding")
    if tuple(designated_inputs) != normalized.inputs:
        raise PhysicalLoweringError("designated input bindings do not match input order")
    if tuple(designated_constants) != normalized.constants:
        raise PhysicalLoweringError("designated constant bindings do not match constant order")
    if tuple(designated_outputs) != normalized.outputs:
        raise PhysicalLoweringError("designated output bindings do not match output order")
    for name, row in {**designated_inputs, **designated_constants}.items():
        if bindings[name] != row:
            raise PhysicalLoweringError(f"protected binding for {name!r} is inconsistent")

    if lowered.removed_exports != normalized.removed_exports:
        raise PhysicalLoweringError("removed terminal-export metadata is inconsistent")
    if len(lowered.primitives) != len(normalized.retained_primitives):
        raise PhysicalLoweringError("lowered trace does not contain exactly the retained prefix")
    for sequence_index, (physical, symbolic, original_index) in enumerate(
        zip(
            lowered.primitives,
            normalized.retained_primitives,
            normalized.retained_original_indices,
        )
    ):
        if (
            physical.opcode,
            physical.symbolic_rows,
            physical.original_index,
            physical.stage,
        ) != (symbolic.op, symbolic.rows, original_index, symbolic.stage):
            raise PhysicalLoweringError(
                f"lowered primitive {sequence_index} opcode or provenance differs from retained trace"
            )
        expected_rows = tuple(bindings[name] for name in symbolic.rows)
        if physical.physical_rows != expected_rows:
            raise PhysicalLoweringError(
                f"lowered primitive {sequence_index} operands differ from identity bindings"
            )
        if physical.opcode != "NOT" and len(set(physical.physical_rows)) != len(
            physical.physical_rows
        ):
            raise PhysicalLoweringError(
                f"lowered primitive {sequence_index} has aliased physical roles"
            )

    intervals = normalized.work_intervals
    for left_index, left_interval in enumerate(intervals):
        for right_interval in intervals[left_index + 1 :]:
            overlap = (
                left_interval.first_required <= right_interval.last_required
                and right_interval.first_required <= left_interval.last_required
            )
            if overlap and bindings[left_interval.symbolic_name] == bindings[
                right_interval.symbolic_name
            ]:
                raise PhysicalLoweringError(
                    "overlapping work intervals share physical row "
                    f"{bindings[left_interval.symbolic_name]}: "
                    f"{left_interval.symbolic_name}, {right_interval.symbolic_name}"
                )

    protected_rows = list(designated_inputs.values()) + list(designated_constants.values())
    output_rows = list(designated_outputs.values())
    if len(set(protected_rows)) != len(protected_rows):
        raise PhysicalLoweringError("protected physical bindings alias")
    if len(set(output_rows)) != len(output_rows):
        raise PhysicalLoweringError("designated output bindings alias")
    if set(protected_rows) & set(output_rows):
        raise PhysicalLoweringError("protected and designated output bindings overlap")
    if set(protected_rows) & {
        bindings[item.symbolic_name] for item in normalized.work_intervals
    }:
        raise PhysicalLoweringError("protected physical row was reused by work")

    expected_results = normalized.output_to_final_producer
    actual_results = tuple(
        (item.output_name, item.final_producer) for item in lowered.result_bindings
    )
    if actual_results != expected_results:
        raise PhysicalLoweringError("result bindings do not match terminal export relations")
    if len({item.output_name for item in lowered.result_bindings}) != len(
        lowered.result_bindings
    ):
        raise PhysicalLoweringError("duplicate result binding")
    for result in lowered.result_bindings:
        if result.physical_row != designated_outputs[result.output_name]:
            raise PhysicalLoweringError(
                f"result row for {result.output_name!r} is not its designation"
            )
        if bindings[result.final_producer] != result.physical_row:
            raise PhysicalLoweringError(
                f"final producer for {result.output_name!r} is not on its result row"
            )
        if result.output_name in bindings:
            raise PhysicalLoweringError("removed output alias appears as an executable identity")

    work_depth = _independent_closed_interval_depth(intervals)
    protected_count = len(normalized.protected_identities)
    output_count = len(normalized.outputs)
    expected_metrics = {
        "additional_scratch_rows": work_depth - output_count,
        "designated_rows": protected_count + output_count,
        "physical_footprint_rows": len(set(bindings.values())),
        "peak_live_identities": protected_count + work_depth,
    }
    if expected_metrics["physical_footprint_rows"] != protected_count + work_depth:
        raise PhysicalLoweringError("physical binding footprint is not Gate A optimal")
    if lowered.metrics != expected_metrics:
        raise PhysicalLoweringError(
            f"physical allocation metrics are inconsistent: expected {expected_metrics}, "
            f"got {lowered.metrics}"
        )

    layout = PhysicalRowLayout(
        lowered.local_row_count,
        designated_inputs,
        designated_constants,
        designated_outputs,
    )
    if lower_to_physical(normalized, layout) != lowered:
        raise PhysicalLoweringError("physical allocation is not deterministic canonical lowering")
    return {
        "binding_coverage": True,
        "protected_rows": True,
        "result_designations": True,
        "exact_terminal_export_removal": True,
        "closed_interval_interference": True,
        "primitive_physical_distinctness": True,
        "row_bounds": True,
        "deterministic_allocation": True,
        "gate_a_optimum": True,
        "work_interval_depth": work_depth,
        "allocation_metrics": expected_metrics,
    }


def _verify_physical(builder, lowered, initial, lanes, symbolic_raw):
    structural = validate_physical_lowering(builder, lowered)
    physical_initial = {
        lowered.bindings[name]: value for name, value in initial.items()
    }
    physical_rows = execute_physical(lowered, physical_initial, lanes)
    results = extract_physical_results(lowered, physical_rows)
    physical_raw = unpack(
        [results[output] for output in builder.outputs["R"]], lanes
    )
    mismatches = sum(
        symbolic != physical for symbolic, physical in zip(symbolic_raw, physical_raw)
    )
    if mismatches:
        raise AssertionError(f"symbolic/physical replay differs for {mismatches} lanes")
    for name, value in initial.items():
        if physical_rows[lowered.bindings[name]] != value:
            raise AssertionError(f"protected physical value changed for {name}")
    structural.update(
        {
            "pairs": lanes,
            "reference_symbolic_physical_mismatches": 0,
            "symbolic_physical_mismatches": 0,
            "input_constant_preservation": True,
            "output_placement": True,
        }
    )
    return structural


def verify(name, builder, path, info, library=False, lowered=None):
    left, right, lanes, rows, raw = _execute_and_replay(builder, path, info)
    width = getattr(builder, "width", 8)
    initial = dict(zip(builder.inputs, pack(left, width) + pack(right, width)))
    initial.update(
        {
            row: (1 << lanes) - 1 if value else 0
            for row, value in info["constants"].items()
        }
    )
    report = {
        "pairs": lanes,
        "serialized_trace_replay_all_rows_equal": True,
        "input_constant_preservation": True,
        "structure_check": "passed",
    }

    if not name.startswith("fp8-"):
        report.update(
            _verify_integer(name, builder, left, right, lanes, rows, raw, library)
        )
        if lowered is not None:
            report["physical_lowering"] = _verify_physical(
                builder, lowered, initial, lanes, raw
            )
        return report

    format_ = FORMATS[builder.format_name]
    if name.endswith("add"):
        details, domain = _verify_fp8_add(
            name, builder, format_, path, left, right, lanes, rows, raw
        )
    else:
        details, domain = _verify_fp8_mul(builder, format_, left, right, raw)
    report.update(details)

    if library:
        _add_library_comparison(name, format_, left, right, raw, domain, report)
    if lowered is not None:
        report["physical_lowering"] = _verify_physical(
            builder, lowered, initial, lanes, raw
        )
    return report
