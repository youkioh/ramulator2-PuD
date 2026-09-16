"""Functional replay of lowered PuD primitives over integer local-row IDs."""

from __future__ import annotations

from itertools import combinations
from typing import Mapping

from .lowering import PhysicalLoweredProgram, PhysicalLoweringError


def _validate_roles(opcode: str, rows: tuple[int, ...], index: int) -> None:
    required = {"NOT": 1, "TRA": 3, "5RA": 5}
    if opcode in ("RowCopy", "NOT_COPY"):
        if len(rows) < 2:
            raise PhysicalLoweringError(
                f"lowered primitive {index}: {opcode} requires a source and destination"
            )
    elif opcode in required:
        if len(rows) != required[opcode]:
            raise PhysicalLoweringError(
                f"lowered primitive {index}: {opcode} requires "
                f"{required[opcode]} physical row role(s)"
            )
    else:
        raise PhysicalLoweringError(
            f"lowered primitive {index}: unsupported opcode {opcode!r}"
        )
    if opcode != "NOT" and len(set(rows)) != len(rows):
        raise PhysicalLoweringError(
            f"lowered primitive {index}: {opcode} physical row roles must be pairwise distinct"
        )


def execute_physical(
    lowered_program: PhysicalLoweredProgram,
    initial_physical_rows: Mapping[int, int],
    lanes: int,
) -> dict[int, int]:
    """Replay a local-row-only lowered trace using bit-sliced lane words."""

    if not isinstance(lowered_program, PhysicalLoweredProgram):
        raise PhysicalLoweringError("lowered_program must be a PhysicalLoweredProgram")
    if isinstance(lanes, bool) or not isinstance(lanes, int) or lanes <= 0:
        raise PhysicalLoweringError("lanes must be a positive integer")
    rows: dict[int, int] = {}
    mask = (1 << lanes) - 1
    for row, value in initial_physical_rows.items():
        if isinstance(row, bool) or not isinstance(row, int):
            raise PhysicalLoweringError("initial physical storage keys must be integer local rows")
        if not 0 <= row < lowered_program.local_row_count:
            raise PhysicalLoweringError(
                f"initial physical row {row} is outside [0, {lowered_program.local_row_count})"
            )
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= mask:
            raise PhysicalLoweringError(
                f"initial physical row {row} value must fit within {lanes} lanes"
            )
        rows[row] = value

    protected_rows = {
        **dict(lowered_program.designated_inputs),
        **dict(lowered_program.designated_constants),
    }
    missing_protected = set(protected_rows.values()) - set(rows)
    if missing_protected:
        raise PhysicalLoweringError(
            "missing initialized protected physical rows: "
            + ", ".join(str(row) for row in sorted(missing_protected))
        )
    protected_initial = {row: rows[row] for row in protected_rows.values()}

    for sequence_index, primitive in enumerate(lowered_program.primitives):
        physical = primitive.physical_rows
        if any(isinstance(row, bool) or not isinstance(row, int) for row in physical):
            raise PhysicalLoweringError(
                f"lowered primitive {sequence_index}: execution operands must be integer rows"
            )
        if any(not 0 <= row < lowered_program.local_row_count for row in physical):
            raise PhysicalLoweringError(
                f"lowered primitive {sequence_index}: physical operand is out of range"
            )
        _validate_roles(primitive.opcode, physical, sequence_index)
        if primitive.opcode in ("RowCopy", "NOT_COPY"):
            reads = physical[:1]
        else:
            reads = physical
        missing = set(reads) - set(rows)
        if missing:
            raise PhysicalLoweringError(
                f"lowered primitive {sequence_index}: uninitialized physical read row(s): "
                + ", ".join(str(row) for row in sorted(missing))
            )

        if primitive.opcode in ("RowCopy", "NOT_COPY"):
            value = rows[physical[0]]
            if primitive.opcode == "NOT_COPY":
                value ^= mask
                rows[physical[0]] = value
            for destination in physical[1:]:
                rows[destination] = value
        elif primitive.opcode == "NOT":
            rows[physical[0]] ^= mask
        else:
            old_values = [rows[row] for row in physical]
            value = 0
            for group in combinations(old_values, len(old_values) // 2 + 1):
                term = mask
                for word in group:
                    term &= word
                value |= term
            for row in physical:
                rows[row] = value

    changed = [row for row, value in protected_initial.items() if rows.get(row) != value]
    if changed:
        raise PhysicalLoweringError(
            "protected physical rows changed during replay: "
            + ", ".join(str(row) for row in sorted(changed))
        )
    missing_results = {
        item.physical_row for item in lowered_program.result_bindings
    } - set(rows)
    if missing_results:
        raise PhysicalLoweringError(
            "result physical rows were not initialized by replay: "
            + ", ".join(str(row) for row in sorted(missing_results))
        )
    return rows


def extract_physical_results(
    lowered_program: PhysicalLoweredProgram, final_physical_rows: Mapping[int, int]
) -> dict[str, int]:
    """Read outputs only through their designated result bindings."""

    results = {}
    for binding in lowered_program.result_bindings:
        try:
            results[binding.output_name] = final_physical_rows[binding.physical_row]
        except KeyError as error:
            raise PhysicalLoweringError(
                f"result row {binding.physical_row} for {binding.output_name!r} is absent"
            ) from error
    return results
