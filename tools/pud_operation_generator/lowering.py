"""Analysis for deterministic local-row lowering of symbolic PuD traces."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
from types import MappingProxyType
from typing import Iterable
from typing import Mapping

from .core import Primitive, validate_structure


DEFAULT_LOCAL_ROW_COUNT = 1024


class PhysicalLoweringError(ValueError):
    """Raised when a symbolic trace cannot be physically lowered."""


@dataclass(frozen=True)
class PrimitiveEffects:
    """Old-value reads and writes performed at one closed command point."""

    reads: tuple[str, ...]
    writes: tuple[str, ...]


@dataclass(frozen=True)
class LiveInterval:
    """One identity's inclusive lifetime in retained-command coordinates."""

    symbolic_name: str
    first_required: int
    last_required: int


@dataclass(frozen=True)
class RemovedExport:
    """A validated terminal output RowCopy removed by physical lowering."""

    original_index: int
    output_name: str
    final_producer: str
    stage: str


@dataclass(frozen=True)
class NormalizedProgram:
    """Immutable analysis view derived from a Builder's symbolic trace."""

    original_primitive_count: int
    retained_primitives: tuple[Primitive, ...]
    retained_original_indices: tuple[int, ...]
    effects: tuple[PrimitiveEffects, ...]
    inputs: tuple[str, ...]
    constants: tuple[str, ...]
    outputs: tuple[str, ...]
    protected_identities: tuple[str, ...]
    output_to_final_producer: tuple[tuple[str, str], ...]
    removed_exports: tuple[RemovedExport, ...]
    protected_intervals: tuple[LiveInterval, ...]
    work_intervals: tuple[LiveInterval, ...]
    completion_point: int

    @property
    def output_producers(self) -> dict[str, str]:
        return dict(self.output_to_final_producer)

    @property
    def intervals(self) -> tuple[LiveInterval, ...]:
        return self.protected_intervals + self.work_intervals


@dataclass(frozen=True)
class PhysicalRowLayout:
    """Exact caller-designated local rows within one execution context."""

    local_row_count: int
    inputs: Mapping[str, int]
    constants: Mapping[str, int]
    outputs: Mapping[str, int]
    work: Mapping[str, int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))
        object.__setattr__(self, "constants", MappingProxyType(dict(self.constants)))
        object.__setattr__(self, "outputs", MappingProxyType(dict(self.outputs)))
        object.__setattr__(
            self, "work", MappingProxyType({} if self.work is None else dict(self.work))
        )


@dataclass(frozen=True)
class PhysicalAllocation:
    """Deterministic optimal binding result before trace materialization."""

    normalized: NormalizedProgram
    layout: PhysicalRowLayout
    identity_bindings: tuple[tuple[str, int], ...]
    work_abstract_colors: tuple[tuple[str, int], ...]
    color_to_local_row: tuple[tuple[int, int], ...]
    additional_scratch_rows: int
    designated_rows: int
    physical_footprint_rows: int
    peak_live_identities: int

    @property
    def bindings(self) -> dict[str, int]:
        return dict(self.identity_bindings)


@dataclass(frozen=True)
class LoweredPrimitive:
    """One executable primitive over integer local-row IDs."""

    opcode: str
    physical_rows: tuple[int, ...]
    symbolic_rows: tuple[str, ...]
    original_index: int
    stage: str

    def to_dict(self) -> dict:
        return {
            "opcode": self.opcode,
            "physical_rows": list(self.physical_rows),
            "symbolic_rows": list(self.symbolic_rows),
            "original_index": self.original_index,
            "stage": self.stage,
        }

    @classmethod
    def from_dict(cls, value: Mapping) -> "LoweredPrimitive":
        return cls(
            opcode=value["opcode"],
            physical_rows=tuple(value["physical_rows"]),
            symbolic_rows=tuple(value["symbolic_rows"]),
            original_index=value["original_index"],
            stage=value["stage"],
        )


@dataclass(frozen=True)
class ResultBinding:
    """One output alias joined to its final producer and designated row."""

    output_name: str
    final_producer: str
    physical_row: int

    def to_dict(self) -> dict:
        return {
            "output_name": self.output_name,
            "final_producer": self.final_producer,
            "physical_row": self.physical_row,
        }

    @classmethod
    def from_dict(cls, value: Mapping) -> "ResultBinding":
        return cls(value["output_name"], value["final_producer"], value["physical_row"])


@dataclass(frozen=True)
class PhysicalLoweredProgram:
    """Complete local-row-only physical lowering artifact."""

    primitives: tuple[LoweredPrimitive, ...]
    identity_bindings: tuple[tuple[str, int], ...]
    designated_inputs: tuple[tuple[str, int], ...]
    designated_constants: tuple[tuple[str, int], ...]
    designated_outputs: tuple[tuple[str, int], ...]
    result_bindings: tuple[ResultBinding, ...]
    removed_exports: tuple[RemovedExport, ...]
    local_row_count: int
    additional_scratch_rows: int
    designated_rows: int
    physical_footprint_rows: int
    peak_live_identities: int

    @property
    def bindings(self) -> dict[str, int]:
        return dict(self.identity_bindings)

    @property
    def metrics(self) -> dict[str, int]:
        return {
            "additional_scratch_rows": self.additional_scratch_rows,
            "designated_rows": self.designated_rows,
            "physical_footprint_rows": self.physical_footprint_rows,
            "peak_live_identities": self.peak_live_identities,
        }

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "kind": "pud-physical-lowered-program",
            "local_row_count": self.local_row_count,
            "local_row_scope": (
                "Row numbers are local to a caller-selected execution context; "
                "they are not complete canonical Ramulator addresses."
            ),
            "designated_bindings": {
                "inputs": dict(self.designated_inputs),
                "constants": dict(self.designated_constants),
                "outputs": dict(self.designated_outputs),
            },
            "output_to_final_producer": {
                item.output_name: item.final_producer for item in self.result_bindings
            },
            "result_bindings": [item.to_dict() for item in self.result_bindings],
            "identity_bindings": dict(self.identity_bindings),
            "removed_terminal_exports": [
                {
                    "original_index": item.original_index,
                    "output_name": item.output_name,
                    "final_producer": item.final_producer,
                    "stage": item.stage,
                }
                for item in self.removed_exports
            ],
            "lowered_primitives": [item.to_dict() for item in self.primitives],
            "allocation_metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, value: Mapping) -> "PhysicalLoweredProgram":
        if value.get("schema_version") != 1 or value.get("kind") != "pud-physical-lowered-program":
            raise PhysicalLoweringError("unsupported physical-lowered artifact schema")
        designated = value["designated_bindings"]
        metrics = value["allocation_metrics"]
        return cls(
            primitives=tuple(
                LoweredPrimitive.from_dict(item) for item in value["lowered_primitives"]
            ),
            identity_bindings=tuple(value["identity_bindings"].items()),
            designated_inputs=tuple(designated["inputs"].items()),
            designated_constants=tuple(designated["constants"].items()),
            designated_outputs=tuple(designated["outputs"].items()),
            result_bindings=tuple(
                ResultBinding.from_dict(item) for item in value["result_bindings"]
            ),
            removed_exports=tuple(
                RemovedExport(
                    item["original_index"],
                    item["output_name"],
                    item["final_producer"],
                    item["stage"],
                )
                for item in value["removed_terminal_exports"]
            ),
            local_row_count=value["local_row_count"],
            additional_scratch_rows=metrics["additional_scratch_rows"],
            designated_rows=metrics["designated_rows"],
            physical_footprint_rows=metrics["physical_footprint_rows"],
            peak_live_identities=metrics["peak_live_identities"],
        )


def primitive_effects(primitive: Primitive, index: int | None = None) -> PrimitiveEffects:
    """Return exact symbolic old-value reads and writes for one primitive."""

    op = primitive.op
    rows = primitive.rows
    location = "primitive" if index is None else f"primitive {index}"
    if not rows or any(not isinstance(row, str) or not row for row in rows):
        raise PhysicalLoweringError(f"{location}: row roles must be nonempty names")
    if len(set(rows)) != len(rows):
        raise PhysicalLoweringError(f"{location}: aliased symbolic row roles")
    if op == "RowCopy":
        if len(rows) < 2:
            raise PhysicalLoweringError(f"{location}: RowCopy requires a source and destination")
        return PrimitiveEffects(rows[:1], rows[1:])
    if op == "NOT_COPY":
        if len(rows) < 2:
            raise PhysicalLoweringError(f"{location}: NOT_COPY requires a source and destination")
        return PrimitiveEffects(rows[:1], rows)
    required = {"NOT": 1, "TRA": 3, "5RA": 5}
    if op not in required:
        raise PhysicalLoweringError(f"{location}: unsupported primitive opcode {op!r}")
    if len(rows) != required[op]:
        raise PhysicalLoweringError(
            f"{location}: {op} requires {required[op]} row role(s), got {len(rows)}"
        )
    return PrimitiveEffects(rows, rows)


def _declared_outputs(builder) -> tuple[str, ...]:
    groups = getattr(builder, "outputs", None)
    if not isinstance(groups, dict):
        raise PhysicalLoweringError("builder outputs must be an ordered mapping of output lists")
    outputs: list[str] = []
    for label, names in groups.items():
        if not isinstance(names, (list, tuple)):
            raise PhysicalLoweringError(f"output group {label!r} must be a list of names")
        outputs.extend(names)
    if len(set(outputs)) != len(outputs):
        raise PhysicalLoweringError("declared output names must be unique")
    return tuple(outputs)


def _record_requirements(
    effects: Iterable[PrimitiveEffects], protected: set[str]
) -> tuple[dict[str, int], dict[str, int], set[str]]:
    first: dict[str, int] = {}
    last: dict[str, int] = {}
    written: set[str] = set()
    defined = set(protected)
    for index, effect in enumerate(effects):
        missing = set(effect.reads) - defined
        if missing:
            raise PhysicalLoweringError(
                f"primitive {index}: read before write: {', '.join(sorted(missing))}"
            )
        overwritten = set(effect.writes) & protected
        if overwritten:
            raise PhysicalLoweringError(
                f"primitive {index}: protected identity overwritten: "
                f"{', '.join(sorted(overwritten))}"
            )
        for name in effect.reads + effect.writes:
            first.setdefault(name, index)
            last[name] = index
        defined.update(effect.writes)
        written.update(effect.writes)
    return first, last, written


def analyze_physical_lowering(builder) -> NormalizedProgram:
    """Validate and normalize one fixed symbolic trace without mutating it."""

    trace = tuple(getattr(builder, "trace", ()))
    if any(not isinstance(item, Primitive) for item in trace):
        raise PhysicalLoweringError("builder trace must contain Primitive records")
    inputs = tuple(getattr(builder, "inputs", ()))
    constants_map = getattr(builder, "constants", {})
    if not isinstance(constants_map, dict):
        raise PhysicalLoweringError("builder constants must be a mapping")
    constants = tuple(constants_map)
    if len(set(inputs)) != len(inputs):
        raise PhysicalLoweringError("input names must be unique")
    if len(set(constants)) != len(constants):
        raise PhysicalLoweringError("constant names must be unique")
    if set(inputs) & set(constants):
        raise PhysicalLoweringError("input and constant names must be disjoint")
    outputs = _declared_outputs(builder)
    protected = set(inputs) | set(constants)
    if protected & set(outputs):
        raise PhysicalLoweringError("output names must be fresh and not protected")

    all_effects = tuple(primitive_effects(item, index) for index, item in enumerate(trace))
    # Retain the existing validator as an independent golden structural check.
    try:
        validate_structure(trace, inputs, constants_map, outputs)
    except (AssertionError, KeyError, TypeError) as error:
        raise PhysicalLoweringError(f"symbolic structure validation failed: {error}") from error

    export_count = len(outputs)
    if export_count > len(trace):
        raise PhysicalLoweringError("missing terminal output-export RowCopy suffix")
    retained_count = len(trace) - export_count
    suffix = trace[retained_count:]
    removed: list[RemovedExport] = []
    for offset, (output, primitive) in enumerate(zip(outputs, suffix)):
        index = retained_count + offset
        if primitive.op != "RowCopy" or len(primitive.rows) != 2:
            raise PhysicalLoweringError(
                f"output {output!r}: terminal export at primitive {index} must be "
                "a single-destination RowCopy"
            )
        source, destination = primitive.rows
        if destination != output:
            raise PhysicalLoweringError(
                f"output {output!r}: missing or out-of-order terminal export at primitive {index}"
            )
        removed.append(RemovedExport(index, output, source, primitive.stage))

    retained = trace[:retained_count]
    retained_effects = all_effects[:retained_count]
    output_set = set(outputs)
    for index, primitive in enumerate(retained):
        used_outputs = set(primitive.rows) & output_set
        if used_outputs:
            raise PhysicalLoweringError(
                f"primitive {index}: output name used or defined before terminal export: "
                f"{', '.join(sorted(used_outputs))}"
            )
    for index, primitive in enumerate(suffix, start=retained_count):
        source = primitive.rows[0] if primitive.rows else None
        if source in output_set:
            raise PhysicalLoweringError(
                f"primitive {index}: output name {source!r} is read by an export"
            )

    final_producers = tuple(item.final_producer for item in removed)
    if len(set(final_producers)) != len(final_producers):
        raise PhysicalLoweringError("terminal exports must have pairwise-distinct final producers")
    protected_producers = set(final_producers) & protected
    if protected_producers:
        raise PhysicalLoweringError(
            "terminal export final producers must be nonprotected work identities: "
            + ", ".join(sorted(protected_producers))
        )

    first, last, written = _record_requirements(retained_effects, protected)
    missing_producers = set(final_producers) - written
    if missing_producers:
        raise PhysicalLoweringError(
            "terminal export final producers must be defined by the retained trace: "
            + ", ".join(sorted(missing_producers))
        )

    completion = retained_count
    for producer in final_producers:
        last[producer] = completion
    work_names = sorted((set(first) | set(last)) - protected - output_set)
    work_intervals = tuple(
        LiveInterval(name, first[name], last[name]) for name in work_names
    )
    protected_names = tuple(inputs + constants)
    protected_intervals = tuple(
        LiveInterval(name, -1, completion) for name in protected_names
    )

    return NormalizedProgram(
        original_primitive_count=len(trace),
        retained_primitives=retained,
        retained_original_indices=tuple(range(retained_count)),
        effects=retained_effects,
        inputs=inputs,
        constants=constants,
        outputs=outputs,
        protected_identities=protected_names,
        output_to_final_producer=tuple(
            (item.output_name, item.final_producer) for item in removed
        ),
        removed_exports=tuple(removed),
        protected_intervals=protected_intervals,
        work_intervals=work_intervals,
        completion_point=completion,
    )


def make_default_physical_layout(
    builder_or_normalized, local_row_count: int = DEFAULT_LOCAL_ROW_COUNT
) -> PhysicalRowLayout:
    """Designate protected and output rows consecutively from local row zero.

    The 1,024-row default is the current DDR4/MIMDRAM model default, not a
    universal DRAM property. Work identities are deliberately left unassigned
    for ``lower_to_physical`` to allocate.
    """

    normalized = (
        builder_or_normalized
        if isinstance(builder_or_normalized, NormalizedProgram)
        else analyze_physical_lowering(builder_or_normalized)
    )
    next_row = 0
    inputs = {}
    for name in normalized.inputs:
        inputs[name] = next_row
        next_row += 1
    constants = {}
    for name in normalized.constants:
        constants[name] = next_row
        next_row += 1
    outputs = {}
    for name in normalized.outputs:
        outputs[name] = next_row
        next_row += 1
    layout = PhysicalRowLayout(local_row_count, inputs, constants, outputs)
    _validate_layout(normalized, layout)
    return layout


def _validate_layout(
    normalized: NormalizedProgram, layout: PhysicalRowLayout
) -> None:
    if isinstance(layout.local_row_count, bool) or not isinstance(
        layout.local_row_count, int
    ) or layout.local_row_count <= 0:
        raise PhysicalLoweringError("local_row_count must be a positive integer")
    if layout.work:
        raise PhysicalLoweringError(
            "arbitrary work-identity precoloring is unsupported: "
            + ", ".join(sorted(layout.work))
        )

    expected = {
        "inputs": set(normalized.inputs),
        "constants": set(normalized.constants),
        "outputs": set(normalized.outputs),
    }
    mappings = {
        "inputs": layout.inputs,
        "constants": layout.constants,
        "outputs": layout.outputs,
    }
    for category, mapping in mappings.items():
        actual = set(mapping)
        missing = expected[category] - actual
        extra = actual - expected[category]
        if missing or extra:
            details = []
            if missing:
                details.append("missing " + ", ".join(sorted(missing)))
            if extra:
                details.append("extra " + ", ".join(sorted(extra)))
            raise PhysicalLoweringError(
                f"layout {category} keys do not match the program: {'; '.join(details)}"
            )
        for name, row in mapping.items():
            if isinstance(row, bool) or not isinstance(row, int):
                raise PhysicalLoweringError(
                    f"layout {category} row for {name!r} must be an integer"
                )
            if not 0 <= row < layout.local_row_count:
                raise PhysicalLoweringError(
                    f"layout {category} row for {name!r} ({row}) is outside "
                    f"[0, {layout.local_row_count})"
                )

    protected_items = list(layout.inputs.items()) + list(layout.constants.items())
    protected_rows = [row for _, row in protected_items]
    if len(set(protected_rows)) != len(protected_rows):
        raise PhysicalLoweringError("protected input/constant rows must be pairwise distinct")
    output_rows = list(layout.outputs.values())
    if len(set(output_rows)) != len(output_rows):
        raise PhysicalLoweringError("designated output rows must be pairwise distinct")
    overlap = set(protected_rows) & set(output_rows)
    if overlap:
        raise PhysicalLoweringError(
            "protected and designated output rows must be disjoint: "
            + ", ".join(str(row) for row in sorted(overlap))
        )


def maximum_interval_depth(intervals: Iterable[LiveInterval]) -> int:
    """Return the maximum overlap of closed intervals."""

    intervals = tuple(intervals)
    if not intervals:
        return 0
    events: list[tuple[int, int]] = []
    for interval in intervals:
        events.append((interval.first_required, 1))
        # Ends sort after starts at the same point, preserving closed overlap.
        events.append((interval.last_required, -1))
    active = peak = 0
    for _, delta in sorted(events, key=lambda item: (item[0], -item[1])):
        active += delta
        peak = max(peak, active)
    return peak


def allocate_physical_rows(
    builder_or_normalized, layout: PhysicalRowLayout
) -> PhysicalAllocation:
    """Optimally color normalized work intervals and assign local row IDs."""

    normalized = (
        builder_or_normalized
        if isinstance(builder_or_normalized, NormalizedProgram)
        else analyze_physical_lowering(builder_or_normalized)
    )
    if not isinstance(layout, PhysicalRowLayout):
        raise PhysicalLoweringError("layout must be a PhysicalRowLayout")
    _validate_layout(normalized, layout)

    active: list[tuple[int, int]] = []
    free_colors: list[int] = []
    next_color = 0
    identity_colors: dict[str, int] = {}
    for interval in sorted(
        normalized.work_intervals,
        key=lambda item: (
            item.first_required,
            item.last_required,
            item.symbolic_name,
        ),
    ):
        while active and active[0][0] < interval.first_required:
            _, color = heapq.heappop(active)
            heapq.heappush(free_colors, color)
        if free_colors:
            color = heapq.heappop(free_colors)
        else:
            color = next_color
            next_color += 1
        identity_colors[interval.symbolic_name] = color
        heapq.heappush(active, (interval.last_required, color))

    color_count = next_color
    work_depth = maximum_interval_depth(normalized.work_intervals)
    if color_count != work_depth:
        raise AssertionError(
            f"interval coloring used {color_count} colors at depth {work_depth}"
        )

    producer_by_output = dict(normalized.output_to_final_producer)
    final_colors = [identity_colors[producer] for producer in producer_by_output.values()]
    if len(set(final_colors)) != len(final_colors):
        raise AssertionError("overlapping final producers received the same color")

    color_rows: dict[int, int] = {}
    for output, producer in normalized.output_to_final_producer:
        color_rows[identity_colors[producer]] = layout.outputs[output]

    designated_physical_rows = (
        set(layout.inputs.values())
        | set(layout.constants.values())
        | set(layout.outputs.values())
    )
    scratch_colors = [color for color in range(color_count) if color not in color_rows]
    eligible_rows = (
        row
        for row in range(layout.local_row_count)
        if row not in designated_physical_rows
    )
    for color in scratch_colors:
        try:
            color_rows[color] = next(eligible_rows)
        except StopIteration as error:
            raise PhysicalLoweringError(
                f"insufficient local-row capacity: need {len(scratch_colors)} "
                "additional scratch rows after caller designations"
            ) from error

    protected_bindings = {
        **dict(layout.inputs),
        **dict(layout.constants),
    }
    work_bindings = {
        name: color_rows[color] for name, color in identity_colors.items()
    }
    bindings = {**protected_bindings, **work_bindings}
    output_count = len(normalized.outputs)
    protected_count = len(normalized.protected_identities)
    additional_scratch = color_count - output_count
    designated_count = protected_count + output_count
    footprint = len(set(bindings.values()))
    peak_live = protected_count + work_depth
    if additional_scratch < 0:
        raise AssertionError("more output producers than work colors")
    if footprint != protected_count + color_count or peak_live != footprint:
        raise AssertionError("physical allocation metric invariant failed")

    return PhysicalAllocation(
        normalized=normalized,
        layout=layout,
        identity_bindings=tuple(sorted(bindings.items())),
        work_abstract_colors=tuple(sorted(identity_colors.items())),
        color_to_local_row=tuple(sorted(color_rows.items())),
        additional_scratch_rows=additional_scratch,
        designated_rows=designated_count,
        physical_footprint_rows=footprint,
        peak_live_identities=peak_live,
    )


def lower_to_physical(
    builder_or_normalized, layout: PhysicalRowLayout
) -> PhysicalLoweredProgram:
    """Allocate and materialize a new physical trace in original order."""

    allocation = allocate_physical_rows(builder_or_normalized, layout)
    normalized = allocation.normalized
    bindings = allocation.bindings
    expected_identities = set(normalized.protected_identities) | {
        item.symbolic_name for item in normalized.work_intervals
    }
    if set(bindings) != expected_identities:
        raise AssertionError("physical identity-binding coverage mismatch")

    primitives = tuple(
        LoweredPrimitive(
            opcode=primitive.op,
            physical_rows=tuple(bindings[name] for name in primitive.rows),
            symbolic_rows=primitive.rows,
            original_index=original_index,
            stage=primitive.stage,
        )
        for primitive, original_index in zip(
            normalized.retained_primitives, normalized.retained_original_indices
        )
    )
    result_bindings = tuple(
        ResultBinding(output, producer, layout.outputs[output])
        for output, producer in normalized.output_to_final_producer
    )
    for result in result_bindings:
        if bindings[result.final_producer] != result.physical_row:
            raise AssertionError("final producer is not bound to its designated output row")

    return PhysicalLoweredProgram(
        primitives=primitives,
        identity_bindings=allocation.identity_bindings,
        designated_inputs=tuple((name, layout.inputs[name]) for name in normalized.inputs),
        designated_constants=tuple(
            (name, layout.constants[name]) for name in normalized.constants
        ),
        designated_outputs=tuple(
            (name, layout.outputs[name]) for name in normalized.outputs
        ),
        result_bindings=result_bindings,
        removed_exports=normalized.removed_exports,
        local_row_count=layout.local_row_count,
        additional_scratch_rows=allocation.additional_scratch_rows,
        designated_rows=allocation.designated_rows,
        physical_footprint_rows=allocation.physical_footprint_rows,
        peak_live_identities=allocation.peak_live_identities,
    )
