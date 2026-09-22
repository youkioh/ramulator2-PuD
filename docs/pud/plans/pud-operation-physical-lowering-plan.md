# PuD Operation Physical Lowering Implementation Plan

Status: Complete. Gate A, Work Units 1-6, Gates 1-6, and the final
fresh-context audit passed on 2026-09-10.

Fixed-width INT8 follow-up: completed on 2026-09-14. INT8 ADD/MUL now export
only eight bits while preserving full internal arithmetic; MUL generates and
reduces all 16 columns in order. The existing lowerer is unchanged. Full
package and exhaustive arithmetic/physical validation, lifetime snapshots,
row-reuse/optimality checks, and default/explicit-layout CLI tests passed.
The current metrics below supersede the initial INT8 baselines. The original
milestone's work-unit restrictions below describe that completed milestone,
not this subsequently authorized arithmetic-interface revision.

UINT8 MUL follow-up: the same column-streaming loop now processes all columns
0..15 while retaining the exact 16-bit internal product. A subsequent
fixed-width UINT8 follow-up exports only `R0..R7` for both ADD and MUL, matching
the other GEMV-facing profiles while preserving full-result diagnostic taps.
The current UINT8 symbolic/physical primitive counts are 49/41 for ADD and
600/592 for MUL. Their respective additional temporary-row counts are 5 and
18, and footprints remain 30 and 43.

Fixed-width 4-bit integer follow-up: standalone UINT4 and INT4 ADD/MUL profiles
now use the same full-internal-result, fixed-width-export contract. They export
`R0..R3` and participate in symbolic generation, physical lowering, replay,
and exhaustive 256-pair validation. GEMV integration and packed storage remain
outside this follow-up. Their current baselines are included below.

FP4 follow-up: standalone raw FP4-E2M1 ADD/MUL profiles now participate in
symbolic generation, physical lowering, replay, and exhaustive 256-pair
encoding validation. They retain the existing floating-point normal-domain,
bounded-alignment, and truncation policy. Block scaling, packed storage, and
GEMV integration remain outside this follow-up.

## Goal and completion state

Extend `tools/pud_operation_generator` with a deterministic physical-lowering
path for one fixed symbolic arithmetic trace. The completed milestone will:

- preserve the existing symbolic `Builder` trace as the golden arithmetic
  program;
- remove only validated terminal output-export RowCopies;
- allocate every remaining symbolic identity to one local physical row for its
  complete closed live interval;
- emit an explicit physical-lowered trace and allocation metadata;
- replay the five existing functional primitives by local physical-row number;
  and
- establish, for the original eight 8-bit profiles and all 65,536 input pairs, that
  the arithmetic reference, existing symbolic replay, and physical replay
  agree.

This is one implementation milestone divided into six reviewable work units.
A work-unit gate is a review and verification boundary, not automatically a
Phase, fresh chat, audit, commit, or new modeling decision.

## Authority and recovery order

Before implementing any work unit, read in order:

1. `AGENTS.md`;
2. `docs/pud/references/pud-physical-row-allocation.md`;
3. `docs/pud/decisions/pud-operation-physical-lowering.md`;
4. `docs/pud/decisions/ddr4-pud-unified-substrate.md`;
5. this plan; and
6. the current files under `tools/pud_operation_generator/` named by the work
   unit.

The Accepted physical-lowering decision is normative. This plan selects an
allocator algorithm within that contract; it does not reopen the contract's
modeling choices. If source behavior conflicts with this plan, stop and update
the plan from the Accepted decision rather than weakening the decision.

## Current implementation boundary

The current package has:

- a symbolic `Primitive`/`Builder` trace and symbolic five-primitive replay in
  `core.py`;
- eight builders in `integer.py` and `fp8.py`;
- symbolic text, symbolic C++ fragment, and row-manifest output in
  `artifacts.py`;
- an exhaustive bit-sliced symbolic validator in `validation.py`; and
- a standard-library CLI in `__main__.py`.

`Builder.export()` currently appends one single-destination RowCopy per output,
and all eight builders place that export block at the end. The physical path
must analyze this existing trace without mutating `Builder.trace`, changing
the builders, or making the symbolic interpreter depend on allocation.

## Gate A — allocator proof and selection

### Result

The proposed reduction is valid under the Accepted contract and the explicit
assumptions below. The selected allocator is deterministic optimal interval
partitioning implemented with standard-library sorting and heaps. No graph
solver or heuristic is needed for this milestone.

### Definitions

After validating and removing the terminal output-export suffix, let:

- `H` be the number of protected input and declared-constant identities;
- `O` be the number of outputs;
- `E` be the operation-completion point, immediately after the final retained
  primitive command;
- `I(x) = [first_required(x), last_required(x)]` be the closed interval of a
  remaining nonprotected symbolic work identity `x`;
- `source(Rn)` be the final symbolic producer named by the removed terminal
  `RowCopy(source(Rn), Rn)`; and
- `C` be the minimum number of colors for the work intervals after every
  `source(Rn)` interval is extended through `E`.

Inputs and declared constants occupy their caller-designated rows from entry
through `E`, but are removed from the reusable coloring problem. Output names
are result aliases after lowering, not second physical identities. Each final
producer remains a work identity and is extended through `E`.

### Proof

1. Each work identity has one continuous closed interval because primitive
   order and symbolic identity are fixed and one binding must serve every use
   and destructive update. Two identities conflict exactly when their
   intervals overlap. Including every operand role at its command point also
   makes source/destination and majority participants conflict at that point.
   The work interference graph is therefore an interval graph.
2. Ordinary interval partitioning colors an interval graph with exactly its
   maximum interval depth. With closed endpoints, a color can be released only
   when `old_end < new_start`. Thus the algorithm uses `C`, the minimum number
   of work colors.
3. Every final producer contains `E` after output-lifetime extension. All final
   producers therefore form a clique. Provided the output-to-producer mapping
   is injective, they receive `O` distinct abstract colors in every valid
   coloring.
4. Rename the unique abstract color containing `source(Rn)` to the caller's
   designated `P(Rn)`. Renaming preserves equality and inequality of colors,
   so it preserves every interval conflict. Because final producers have
   distinct colors and designated output rows are distinct, this also
   preserves every output binding. Any earlier identities in such a color end
   before its final producer starts and may legally occupy that output row.
5. Map each of the other `C - O` colors injectively to an otherwise unused
   eligible local row. Protected rows are outside this mapping and designated
   output rows have already been consumed by final-producer colors.
6. For optimality, take any legal allocation under this contract and ignore
   its physical row labels. Its work bindings form a coloring using the `O`
   designated output rows plus `S` additional temporary rows, so
   `O + S >= C`. Hence `S >= C - O`. The construction above attains
   `S = C - O`; it is optimal for the accepted fixed-order,
   identity-preserving problem.

Consequently:

```text
additional_temporary_rows = C - O
designated_rows = H + O
physical_footprint_rows = H + C
```

Let `peak_live_work_identities` mean maximum depth among the colored work
intervals. Then `C = peak_live_work_identities` and:

```text
physical_footprint_rows = H + peak_live_work_identities
```

The Accepted `peak_live_identities` metric includes the protected identities.
Because all `H` protected identities are live throughout the operation:

```text
peak_live_identities = H + peak_live_work_identities
                     = physical_footprint_rows
```

Implementation and artifacts must not add `H` twice: if a work-only peak is
reported internally it must be named as such, while the four public Accepted
metrics retain the definitions above.

### Assumptions that make the proof valid

Normalization and caller validation must establish all of these before the
allocator runs:

- each declared output corresponds, in output-list order, to exactly one
  single-destination RowCopy in one contiguous terminal suffix;
- an output name is fresh at that suffix, is written only by its export, is
  not read by the retained program, and has no independent required final
  identity after export removal;
- final producers are pairwise-distinct nonprotected work identities defined
  by the retained trace;
- every required input, declared constant, and output has exactly one
  caller-provided local-row binding, with no unknown or missing keys;
- protected bindings are in range and pairwise distinct, output bindings are
  in range and pairwise distinct, and the protected and output row sets are
  disjoint;
- caller precoloring does not fix any other work identity; adding arbitrary
  work precoloring would be a different constrained problem and is rejected;
- every local row not occupied by protected bindings is homogeneous and
  eligible for every retained primitive in the already selected execution
  context;
- output rows may hold earlier nonoverlapping temporaries, and non-output
  colors may use any otherwise unused eligible row;
- all identities occupy one unit-sized row, primitive order is fixed, one
  identity has one binding, command points are closed, and no spilling,
  splitting, copy insertion, value-equivalence aliasing, reordering, or
  recomputation is allowed; and
- only protected inputs/constants and designated results are required final
  state. Diagnostic taps and discarded carries remain symbolic validation
  observations and do not extend physical lifetimes.

The first implementation consumer of these assumptions is normalized-program
construction in Work Unit 1. Failure of any assumption must produce a clear
lowering error before allocation; it must not fall back to a heuristic.

### Required edge-case handling

| Edge case | Required result |
| --- | --- |
| Two outputs name the same final symbolic producer | Reject. One identity cannot be bound to two distinct designated output rows, and duplicate output rows are separately illegal. |
| Duplicate designated output rows | Reject. All final producers overlap at `E`, so live outputs require distinct rows. |
| Final producer is an input or declared constant | Reject. Its protected binding cannot equal the disjoint designated output binding required after export removal. |
| Invalid caller precoloring | Reject missing/extra symbolic keys, non-local or out-of-range row IDs, overlapping protected bindings, duplicate output bindings, protected/output overlap, and unsupported precoloring of arbitrary work identities. |
| No-output trace | Accept if otherwise structurally valid. Remove no suffix, set `O = 0`, and obtain `additional_temporary_rows = C` and `physical_footprint_rows = H + C`. An empty retained trace has `C = 0`. |
| Output producer's last ordinary use is early | Extend its interval through `E`; its designated output row cannot be reused after the producer becomes live. |
| One interval ends where another starts | Treat both as live at that command. Do not reuse the color unless `old_end < new_start`. |

### Selected deterministic algorithm

1. Sort work intervals by `(start, end, symbolic_name)`.
2. Maintain an active min-heap keyed by `(end, abstract_color)` and a min-heap
   of free abstract color numbers.
3. Before allocating an interval starting at `start`, release all active
   colors with `end < start`; do not release an interval ending at `start`.
4. Assign the smallest free color, or the next monotonically increasing color
   if none is free, and insert `(end, color)` into the active heap.
5. Assert independently that the number of colors equals maximum work-interval
   depth and that final producers occupy distinct colors.
6. Bind final-producer colors to their caller-designated output rows. In
   ascending abstract-color order, bind all remaining colors to the lowest
   eligible local row not used by any protected or output designation.
7. Fail explicitly if there are fewer than `C - O` such rows.

The tie-breaks affect only deterministic naming, not optimality. Allocation
logic consumes local-row capacity and eligibility only; it has no Ramulator
timing, command-phase, recovery, request-scheduling, Bank, subarray, or
`MatRange` dependency.

### Revalidated baselines of the current traces

A fresh calculation after the integer scheduling and fixed-width revisions
confirmed that every profile has a
valid terminal export suffix, pairwise-distinct nonprotected final producers,
and the following interval-partitioning result. These values are regression
baselines; the implementation recomputes rather than hard-codes them.

| Profile | Retained physical primitives | `H` | `O` | Work colors `C` | Additional temporary rows | Designated rows | Footprint / accepted peak live |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `uint4-add` | 21 | 9 | 4 | 9 | 5 | 13 | 18 |
| `uint4-mul` | 136 | 9 | 4 | 14 | 10 | 13 | 23 |
| `int4-add` | 26 | 9 | 4 | 10 | 6 | 13 | 19 |
| `int4-mul` | 148 | 10 | 4 | 14 | 10 | 14 | 24 |
| `fp4-e2m1-add` | 481 | 10 | 4 | 16 | 12 | 14 | 26 |
| `fp4-e2m1-mul` | 122 | 10 | 4 | 11 | 7 | 14 | 21 |
| `uint8-add` | 41 | 17 | 8 | 13 | 5 | 25 | 30 |
| `uint8-mul` | 592 | 17 | 8 | 26 | 18 | 25 | 43 |
| `int8-add` | 46 | 17 | 8 | 14 | 6 | 25 | 31 |
| `int8-mul` | 612 | 18 | 8 | 26 | 18 | 26 | 44 |
| `fp8-e5m2-add` | 1,045 | 18 | 8 | 25 | 17 | 26 | 43 |
| `fp8-e5m2-mul` | 326 | 18 | 8 | 15 | 7 | 26 | 33 |
| `fp8-e4m3-add` | 1,331 | 18 | 8 | 30 | 22 | 26 | 48 |
| `fp8-e4m3-mul` | 318 | 18 | 8 | 20 | 12 | 26 | 38 |

The historical INT8 ADD baseline had 9 outputs, 5 scratch, 26 designated rows,
and footprint 31. INT8 MUL had 16 outputs, 68 work colors, 52 scratch,
34 designated rows, and footprint 86. Retained arithmetic primitive counts
remain 46 and 612; only export counts and MUL generation order changed.
The historical UINT8 ADD/MUL baselines had 9/16 outputs, 4/10 additional
temporary rows, and 26/33 designated rows respectively. Their retained
arithmetic primitive counts and total footprints are unchanged by selecting
only the low eight public result bits.

All fourteen fit within the accepted 1,024-local-row profile under any valid
in-range choice of distinct designated rows that leaves the listed additional
temporary-row capacity. This is a physical-local-row bound only, not a complete
canonical Ramulator address or a claim about concurrent `MatRange` placement.

## Intended API and artifact boundary

Use small frozen dataclasses or equivalent immutable records in a new
`tools/pud_operation_generator/lowering.py` module. Exact private helper names
may vary, but the public concepts must remain distinct:

- `PhysicalRowLayout`: local-row capacity plus exact input, declared-constant,
  and output designation maps supplied by the caller;
- `NormalizedProgram`: an immutable analysis view over the original symbolic
  trace, including retained primitives, validated terminal exports,
  output-to-final-producer relations, effects, intervals, and protected
  identities;
- `LoweredPrimitive`: opcode, actual local physical operand rows, original
  symbolic operand names, original primitive index, and stage/provenance; and
- `PhysicalLoweredProgram`: lowered primitive sequence, identity bindings,
  designated bindings, result bindings, removed-export metadata, capacity, and
  the four Accepted metrics.

The primary callable boundary should be equivalent to:

```text
analyze_physical_lowering(builder) -> NormalizedProgram
lower_to_physical(builder_or_normalized, PhysicalRowLayout)
    -> PhysicalLoweredProgram
execute_physical(lowered_program, initial_physical_rows, lanes)
    -> final_physical_rows
```

`execute_physical` accepts and returns storage keyed by integer local-row ID.
Result extraction uses each output's designated integer row. Symbolic names in
the lowered object are provenance and diagnostics only; they are not execution
authority.

Add one machine-readable `<profile>.physical.json` artifact when physical
lowering is explicitly requested. It should contain:

- schema version and a physical-lowered kind marker;
- local-row capacity and designated input/constant/output maps;
- output-to-final-producer/result bindings;
- complete symbolic-identity-to-local-row bindings;
- removed terminal-export records with original indices;
- the lowered primitive list with physical operands and symbolic provenance;
- the four allocation metrics; and
- an explicit statement that row numbers are local to a caller-selected
  execution context and are not complete canonical Ramulator addresses.

Do not emit a physical C++ request fragment in this milestone. The later thin
Ramulator adapter must combine local-row numbers with the resolver-selected
Bank/subarray and explicit `MatRange`; the lowering package must not invent
that encoding.

Keep the existing `.primitives.txt`, `.rows.json`, and `.requests.inc` files as
symbolic artifacts. Add an opt-in CLI argument equivalent to
`--physical-layout <json>` whose per-profile records provide
`local_row_count`, `inputs`, `constants`, and `outputs`. Without this argument,
existing symbolic generation and validation behavior remains available. With
it, every selected profile must have an exact valid layout, and the CLI emits
the physical artifact and physical validation result or fails clearly.

## Work Unit 1 — lowering analysis and normalized program

### Expected files

- Add `tools/pud_operation_generator/lowering.py`.
- Add `tools/pud_operation_generator/tests/test_physical_lowering.py`.
- Change `core.py` only if a small shared primitive-effects helper avoids
  inconsistent opcode semantics; do not change `Builder`, `Primitive`, or
  `execute()` behavior.

### Invariants

- The input `Builder.trace` and all contained `Primitive` objects remain
  unchanged.
- Derive explicit read/write effects as follows: RowCopy reads its source and
  writes its destinations; `NOT` reads/writes its row; `NOT_COPY` reads/writes
  its source and writes its destinations; TRA/5RA read/write all participants.
- Validate normal opcode arity, symbolic role distinctness, definition before
  read, and protected-row immutability without weakening
  `validate_structure()`.
- Recognize terminal exports only as the exact ordered suffix of
  single-destination `RowCopy(source, output)` operations corresponding to the
  declared output list. Reject output names used or defined elsewhere,
  nonterminal/missing/multi-destination exports, duplicate outputs, duplicate
  final producers, and protected final producers.
- Preserve original primitive indices and stage strings in the retained view.
- For each retained identity, derive first and last required command. Inputs
  and declared constants are protected from entry through completion; work
  identities get one convex closed interval; final producers extend through
  completion. Output names do not become separate normalized identities.
- Taps and discarded carries do not extend intervals.
- An otherwise valid no-output trace is supported.

### Tests

- Analyze all eight builders without changing trace equality or existing
  primitive counts.
- Assert exact output-to-producer maps, retained prefix lengths, protected
  sets, command effects, interval endpoints, and current baseline work-color
  depths.
- Use synthetic traces to reject every malformed terminal-export pattern and
  the duplicate/protected-producer cases.
- Cover no-output, empty trace, a producer whose last normal use is early, a
  destructive read/write identity, and two intervals sharing a command
  endpoint.
- Run the existing generator tests unchanged.

### Gate 1 completion criteria

Review the normalized-program dump for one integer and one FP8 profile and
confirm that it is derived from, not substituted for, the symbolic trace. All
analysis and negative tests pass, and every Gate A structural assumption is
represented by an explicit check. No allocation or physical execution exists
yet.

### Must not change

Arithmetic builders, symbolic primitive order/counts, symbolic replay,
numeric references, output widths, diagnostic taps, and existing artifact
formats.

## Work Unit 2 — optimal physical local-row allocator

### Expected files

- Extend `tools/pud_operation_generator/lowering.py`.
- Extend `tools/pud_operation_generator/tests/test_physical_lowering.py`.

### Invariants

- Consume exact caller input/constant/output bindings and a positive local-row
  capacity; validate keys, integer row IDs, bounds, uniqueness, and required
  category disjointness before coloring.
- Protected physical rows never enter the reusable pool.
- One symbolic work identity has one binding for its complete interval.
- Designated output rows may host only earlier nonoverlapping temporary
  intervals before their final-producer interval.
- Implement the selected closed-interval heap algorithm and deterministic
  color-to-row renaming exactly as described in Gate A.
- Temporary rows are selected in ascending local-row order after excluding all
  caller-designated rows. Insufficient capacity is an explicit error.
- Report `additional_temporary_rows`, `designated_rows`,
  `physical_footprint_rows`, and inclusive `peak_live_identities` with the
  Accepted meanings.
- Do not spill, split live ranges, insert copies, merge equal values, reorder
  primitives, or consult Ramulator timing.

### Tests

- Assert deterministic identical bindings across repeated lowering and across
  equivalent dictionary insertion orders.
- Check closed same-command endpoints cannot share, while an interval ending
  at `i` can share with one starting at `i+1`.
- Check an output row is reused by an eligible earlier temporary and is not
  reused once its final producer starts.
- Independently calculate maximum interval depth and assert color count,
  `additional_temporary_rows = C - O`, and all four metrics.
- Lock the eight plan-time metric baselines without hard-coding them in the
  allocator.
- Reject insufficient capacity, missing/extra/wrong-category designations,
  out-of-range/non-integer IDs, protected aliases, output aliases,
  protected/output overlap, and arbitrary work precoloring.
- Cover valid no-output allocation and exact-capacity success.

### Gate 2 completion criteria

An independent test-side interval-depth calculation confirms optimality and
all four metrics for synthetic cases and all eight profiles. Failure paths are
deterministic and descriptive. Full diff review finds no graph solver,
heuristic fallback, spilling, timing, or placement-context inference.

### Must not change

The normalized symbolic program, retained primitive sequence, caller's
designated rows, or existing symbolic validation behavior.

## Work Unit 3 — explicit lowered physical trace

### Expected files

- Extend `tools/pud_operation_generator/lowering.py`.
- Update `tools/pud_operation_generator/__init__.py` only for the intended
  public lowering types/functions.
- Extend `tools/pud_operation_generator/tests/test_physical_lowering.py`.

### Invariants

- Materialize a new immutable sequence; never rewrite `Builder.trace` in
  place.
- The physical sequence is the retained symbolic prefix in exactly the same
  order, with exactly the validated terminal exports absent and no other
  insertion, deletion, or opcode change.
- Every executable operand is an integer local-row number. Symbolic operands,
  stage, and original index remain attached solely as provenance.
- Identity bindings cover protected and retained work identities exactly.
  Removed output names are represented through designated/result bindings to
  their final producers, not as false second physical identities.
- The lowered object contains the designated input, constant, and output maps,
  result bindings, removed exports, capacity, and the four metrics.
- The representation contains no Bank, subarray, CellID, `MatRange`, request,
  phase, timing, or scheduling encoding.

### Tests

- Compare every lowered opcode/provenance pair with the corresponding retained
  symbolic primitive for all eight profiles.
- Assert physical operand tuples equal application of the identity-binding map
  and contain no symbolic execution operands.
- Assert each result binding joins output name, final producer, and designated
  row, and that no removed output identity appears in executable bindings.
- Assert only the exact terminal suffix is removed and the original trace is
  byte-for-byte/equality unchanged after lowering.
- Round-trip the lowered dataclasses through their artifact-ready dictionary
  form without losing ordering or integer row identity.

### Gate 3 completion criteria

One integer and one FP8 lowered trace receive manual provenance review, all
eight structural comparisons pass, and the representation is sufficient for
physical replay without consulting symbolic names. It remains local-row-only.

### Must not change

Symbolic artifact contents, primitive semantics, physical allocation results,
or any Ramulator source/API.

## Work Unit 4 — physical functional replay

### Expected files

- Add `tools/pud_operation_generator/physical_replay.py`.
- Extend `tools/pud_operation_generator/tests/test_physical_lowering.py`.
- Export the physical replay entry point from `__init__.py` only if it is part
  of the intended package API.

### Invariants

- Replay storage is `dict[int, int]` (or an equivalent integer-keyed mapping)
  indexed only by actual local physical rows.
- Implement the existing functional leaf semantics: RowCopy snapshots and
  preserves its source; `NOT` inverts in place; `NOT_COPY` snapshots then
  writes the inverted value to source and destinations; MAJ3/TRA and MAJ5/5RA
  snapshot all operands then write their majority to all participants.
- Before executing each primitive, independently require pairwise-distinct
  physical roles for RowCopy, `NOT_COPY`, MAJ3, and MAJ5. `NOT` remains
  single-row in place.
- Require every read/old-value operand to be initialized. Check protected
  input/constant row values at exit.
- Expose results only by reading designated output physical rows from result
  bindings; provenance names never select execution storage.
- Do not model timing, activation phases, recovery, command buses, request
  scheduling, or concurrent mat payloads.

### Tests

- Directed unit tests cover each primitive's snapshot/destructive semantics,
  lane masking, initialization errors, and physical-alias rejection.
- A deliberately malformed lowered trace with symbolically distinct but
  physically aliased roles fails independently of allocator validation.
- A temporary row reused after a nonoverlapping interval behaves correctly;
  same-command reuse fails.
- Selected integer and FP8 cases match symbolic replay through designated
  output rows, while protected physical inputs/constants remain unchanged.
- Symbolic `execute()` tests continue to run independently.

### Gate 4 completion criteria

All five primitives have directed physical-storage tests, illegal physical
aliasing is caught at replay, and selected end-to-end cases use only integer
local-row execution identities. No timing or `MatRange` state appears in the
module.

### Must not change

The symbolic interpreter, its all-symbolic-row diagnostic behavior, arithmetic
references, or Ramulator timing and request code.

## Work Unit 5 — exhaustive physical validation

### Expected files

- Extend `tools/pud_operation_generator/validation.py`.
- Extend `tools/pud_operation_generator/tests/test_physical_lowering.py` and,
  only where appropriate, `tests/test_generator.py`.

### Invariants

- Preserve the current symbolic `verify()` path and its serialized symbolic
  trace equality, tap, discarded-carry, branch/domain, and optional library
  checks.
- Add a physical-validation entry or backward-compatible optional lowered
  argument; callers that do not request physical validation retain existing
  behavior and report fields.
- Use the same bit-sliced 65,536 lanes for symbolic and physical replay.
  Initialize the physical store through designated input/constant row maps and
  extract results through designated output rows.
- For every profile establish explicitly:

  ```text
  arithmetic reference == symbolic replay == physical allocated replay
  ```

- Validate allocation independently of successful value replay: exact binding
  coverage, protected rows, result designations, removed export indices,
  closed-interval interference, physical operand distinctness, row bounds,
  deterministic allocation, all metric recounts, and the Gate A optimum.
- Keep diagnostic tap and discarded-carry validation on the symbolic golden
  path; do not extend their physical lifetimes merely to reproduce the final
  symbolic dictionary.

### Tests

- Exhaustively validate UINT8 ADD/MUL, INT8 ADD/MUL, E5M2 ADD/MUL, and E4M3
  ADD/MUL over all 65,536 input pairs with explicit valid test layouts.
- For each profile assert zero reference/symbolic/physical mismatches, input
  and constant preservation, output placement, exact export removal,
  interference legality, primitive distinctness, deterministic allocation,
  independent peak-depth equality, and the four metric baselines.
- Add negative tests that bypass or corrupt one layer at a time: insufficient
  capacity, illegal precoloring, overlapping interval bindings, wrong result
  binding, retained/misidentified terminal export, aliased physical primitive,
  and inconsistent metrics.
- Run existing symbolic-only exhaustive validation to show it was extended,
  not replaced.

### Gate 5 completion criteria

All eight triple-equality validations pass over 65,536 pairs, every required
allocation and failure property has an independent assertion, and existing
symbolic validation reports remain intact. Review test runtime and avoid
duplicating the full domain more times than needed to establish independent
properties.

### Must not change

INT8/FP8 arithmetic, rounding/domain policy, symbolic serialized replay,
diagnostic semantics, or primitive order.

## Work Unit 6 — artifacts and user surface

### Expected files

- Extend `tools/pud_operation_generator/artifacts.py` and `__main__.py`.
- Update `tools/pud_operation_generator/__init__.py` for the final supported
  API surface.
- Update `tools/pud_operation_generator/README.md`.
- Extend both generator and physical-lowering tests as needed.

### Invariants

- Existing symbolic artifacts remain useful and retain clear symbolic labels.
- Physical output is opt-in through an explicit caller layout; the tool does
  not silently choose input, constant, or output placements.
- `<profile>.physical.json` contains the complete reproducible local-row
  lowering boundary listed above. Serialization is deterministic, and emitted
  metrics are integers independently checked by validation.
- `validation.json` preserves its existing symbolic result and adds a clearly
  named physical-lowering result when requested; do not ambiguously relabel
  symbolic checks as physical.
- CLI diagnostics name the profile and invalid layout/category/row when
  lowering fails.
- README examples distinguish `symbolic program` from
  `physical-lowered program`, document layout JSON and the opt-in CLI/API, and
  state that local-row IDs require a later resolver-aware adapter to become
  canonical Ramulator operands.
- The package remains independently copyable and standard-library-only for
  normal generation/lowering/validation.

### Tests

- Golden/schema-shape tests cover one emitted physical artifact and exact
  deterministic regeneration.
- CLI tests cover all selected layouts, missing per-profile layout, malformed
  JSON/categories, capacity failure, and a successful physical validation.
- Preserve the current CLI without `--physical-layout` and its symbolic files
  and PASS reporting.
- Extend the copied-folder test to exercise physical lowering without sibling
  repository imports.
- Confirm no generated physical artifact claims to be a full Ramulator
  address or request fragment.

### Gate 6 completion criteria

From a clean temporary output directory, a documented command with an explicit
layout emits both clearly distinguished symbolic artifacts and deterministic
physical JSON, and reports exhaustive physical validation success. The copied
package performs the same operation standalone. README, CLI help, API exports,
and artifact schemas agree.

### Must not change

Default symbolic CLI usefulness, existing profile names/contracts and symbolic
filenames, optional NumPy/`ml_dtypes` comparison semantics, or Ramulator source.

## Final fresh-context audit

After Gate 6, start a fresh context and recover authority in the order at the
top of this plan. The audit is independent validation, not a seventh work unit.
It must:

1. inspect the complete milestone diff and confirm changes are confined to the
   generator package, its tests/README, and this plan's progress record;
2. rederive Gate A's assumptions, optimum proof, formulas, and eight baseline
   metrics without trusting allocator-produced metrics;
3. verify exact terminal-export recognition and confirm no other primitive was
   removed, inserted, reordered, or assigned a symbolic execution operand;
4. review allocator determinism, closed endpoints, output-color renaming,
   capacity failure, and every precoloring rejection path;
5. review physical replay snapshot semantics and independent physical-role
   distinctness for all five primitives;
6. run the focused unit suite, all eight 65,536-pair symbolic/physical
   validations, opt-in CLI/artifact checks, and standalone copied-package test;
7. run `git diff --check` and review the final generated schema examples; and
8. confirm that no timing, phase, recovery, scheduling, Bank/subarray/
   `MatRange` encoding, movement, GEMV, amplification, or arithmetic redesign
   entered the implementation.

Audit findings must be fixed and the affected focused/full checks rerun before
the milestone is marked complete.

## Explicitly deferred

This milestone does not implement:

- Ramulator timing integration beyond identifying a later thin adapter;
- `MatRange`-aware concurrent functional payloads;
- LC-MOV or GB-MOV;
- GEMV layout or GEMV macro generation;
- host read/write amplification;
- INT8 or FP8 arithmetic redesign, new special-value behavior, or rounding
  changes;
- general compiler IR, scheduling, reordering, recomputation, spilling,
  live-range splitting, general copy coalescing, or value-equivalence aliasing.

## Milestone handoff

Gate A has no remaining allocator-selection blocker: deterministic heap-based
interval partitioning plus final-color renaming is optimal under the Accepted
contract, with `additional_temporary_rows = C - O` and footprint derived from
protected rows plus work peak liveness. The implementation is organized into
six gated work units: normalized analysis, allocation, explicit lowering,
physical replay, exhaustive validation, and artifacts/user surface.

The expected boundary is a standalone local-row lowering API and one
machine-readable physical JSON artifact per explicitly laid-out profile.
Symbolic programs remain the arithmetic authority; physical programs execute
by integer local row and retain symbolic data only as provenance. No unresolved
engineering issue currently blocks implementation. A violation of any Gate A
assumption is an explicit unsupported-input failure, not an open choice or a
reason to substitute a heuristic.

The next milestone is the MIMDRAM-aware functional/layout layer. It will
consume this physical-lowering result and add the selected execution-context
and layout semantics needed for range-aware payloads; those concerns do not
belong in this plan.
