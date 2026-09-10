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


def verify(name, builder, path, info, library=False):
    left, right, lanes, rows, raw = _execute_and_replay(builder, path, info)
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
    return report
