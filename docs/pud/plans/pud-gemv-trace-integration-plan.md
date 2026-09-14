# PuD GEMV Trace Integration Plan

Status: Complete. The user accepted the HFF-aligned positive-N domain on
2026-09-14. WU1-WU4 gates and the final fresh-context audit passed. The
integration milestone can be closed; no commit was made.

## Authority and recovery

Read `AGENTS.md`, the
[canonical CUDA programming-model specification](../references/gpu-pud-gemv-programming-model.cu)
and its [Markdown summary](../references/gpu-pud-gemv-programming-model.md), the
[physical-row reference](../references/pud-physical-row-allocation.md), and
[MIMDRAM mapping/reduction reference](../references/mimdram-data-mapping-and-vector-reduction.md),
then the Accepted [physical lowering](../decisions/pud-operation-physical-lowering.md),
[placement/payload](../decisions/mimdram-addressing-geometry-and-payload.md),
[reduction](../decisions/mimdram-reduction-placement-and-movement-lowering.md),
[execution/completion](../decisions/mimdram-movement-execution-ownership-and-device.md),
[timing](../decisions/mimdram-movement-timing-and-resource-model.md), and
[unified substrate](../decisions/ddr4-pud-unified-substrate.md) decisions.
The [completed lowering plan](pud-operation-physical-lowering-plan.md) records
prior validation; current source/tests remain the implementation evidence.

The repository `.cu` is the canonical authority for the interfaces and macro
graph; the Markdown reference explains that source. The prototype generator
must implement those semantics without parsing CUDA or consuming the `.cu`
as runtime input. The specification is not a required build target.

## Initial integration audit (gaps now closed)

- All six requested arithmetic profiles already exist with eight output rows.
  `lowering.py` computes PuD micro-operation-level temporary-row requirements and
  retained primitive counts;
  `physical_replay.py` executes lowered arithmetic. Missing: generated JSON/C
  requirements and a restriction to macro-selected PuD micro-operation-level temporary
  rows. The current allocator may consume any nondesignated local row, including another live
  macro workspace; `PhysicalRowLayout.work` does not supply an exact temporary-row selection.
- Missing: explicit INT8/E4M3/E5M2 GEMV profiles, placement, micro-operation
  orchestration, movement lowering, physical trace, and composition validation.
  The supplied specification fixes the arithmetic graph, three macro workspace
  roles, serialized PuD micro-operation-level temporary-row reuse, and forward
  reduction topology.
- The canonical resolver/paired-operand Request path and completion callbacks
  already exist. Existing load/store and external frontends do not consume this
  physical PuD stream. `IMemorySystem::location_resolver()` supplies the installed
  authority; no replacement resolver or controller scheduler is needed.
- The host residual/domain combine is already authorized outside Ramulator.
  Functional validation must include the specification's scalar graph, but
  modeled PuD completion excludes host readout/conversion/arithmetic costs.
  Existing FP8 numerical limitations remain; graph equality does not establish
  general IEEE/OFP8 arithmetic or make zero padding an arithmetic identity.

## Accepted length gate

The [Accepted macro contract](../decisions/pud-gemv-macro-contract.md) requires
N > 0 and N divisible by HFFS_PER_MAT (=4), not MAT_SIZE. N=516 and other
whole-group partial final mats remain supported. Reject arbitrary tails;
introduce no partial-group movement, masking, padding, or host fallback.
This closes the gate before WU2. Reopen only a genuinely new modeling question.

## One integration phase, four sequential work units

The phase invariant is a generator-produced, physically legal PuD GEMV stream
whose functional composition matches the agreed graph and whose every request
completes through the existing unified substrate. Gates are focused checks,
not separate phases or commits. Recheck the decision gate before WU2.

| Unit | Implementation and gate | Progress |
| --- | --- | --- |
| WU1 | Generate six-profile requirements JSON/header from existing analysis/lowering; include input/output, constant, PuD micro-operation-level temporary-row and physical primitive counts. Add only exact static temporary-row selection to the lowerer. Check deterministic generation, exact selected-row use, insufficient/excess counts and illegal rows, preserved default behavior, and focused affected lowering tests. | Passed |
| WU2 | Add three explicit Python GEMV profiles; place inputs/duplicated x, three distinct PuD macro-operation-level temporary-row workspaces, constants and PuD micro-operation-level temporary rows; use `max(ADD, MUL)` for the micro-operation-level requirement. Instantiate existing arithmetic and lower legal LC/GB moves in forward topology order. Emit minimal layout/resources plus one ordered physical Request trace. Check layout legality and the accepted tail policy. | Passed |
| WU3 | Replay the physical composition outside Ramulator, reusing arithmetic replay. Cover one/two/more reachable mats, a partial final mat, and multiple outputs with deterministic inputs. Compare INT8 fixed-width GEMV and each FP8 format's identical scalar MUL/ADD graph, including host completion. Check term coverage, topology, temporary ownership/counts, and profile isolation. | Passed |
| WU4 | Add a thin finite trace frontend using the installed resolver, paired operands and canonical Requests. Wait for completion before issuing dependent work, retain rejected requests for retry, and finish only after the last callback. Validate parsing/translation and complete representative traces for all three profiles with request/command counts using existing harnesses. | Passed |

Trace fields must describe only the selected placement profile/context, ordered
primitive type and row operands, explicit mat range(s), and movement groups,
plus fields required by the current Request contract. Encoding is the versioned `PUD_TRACE 1` stream (profile/ranks header,
then opcode, channel/rank/bank-group/bank, mat endpoints and row/group operands); no GEMV instruction, functional payload, or general compiler IR belongs
in Ramulator. Callback-ordered execution must cover temporary-row reuse as well
as arithmetic and movement dependencies.

After WU4, perform the requested fresh-context audit against the canonical `.cu`,
its summary, Accepted authority, complete diff and focused integration tests. Verify
separate FP8 profiles, generator-owned counts, distinct temporary-row ownership, serialized
same-mat operations, macro-owned scheduling/layout/reduction, and reuse of all
arithmetic/lowering/movement/timing mechanisms. Fix findings, run only directly
affected regressions and `git diff --check`, then assess milestone closure.

## Progress and verification

- The user accepted the length gate; the canonical decision and .cu precondition
  now require positive N divisible by four, including partial final mats.
- WU1: generated six-profile requirements JSON/header and explicit operation
  temporary-row selection. Sixteen focused lowerer/API/standalone tests passed
  (49 subtests), preserving default allocation. Physical artifact schema 2 uses
  `additional_temporary_rows`; no legacy metric alias is emitted.
- WU2: static output row bands hold separate input domains, three macro
  workspaces, constants and the generated maximum micro-operation-level requirement.
  The generator reads the existing C++ placement profile through a thin binding;
  it does not implement another location resolver.
- WU3: 31 focused composition/tail checks passed, including one/two/three mats,
  N=516/1028, multiple outputs and a second domain. Physical arithmetic replay
  matches the scalar graph separately for all profiles. INT8 also matches a flat
  scalar dot product. Alternate unused-cell contents preserve live results.
- WU4: `_ramulator` built; three full representative traces and fifteen
  parsing/location/authority checks passed. Existing command recording and
  controller completion counts agree with the frontend counters:

  | Profile, M=1 N=516 | Requests completed | Command occurrences | Controller cycles |
  | --- | ---: | ---: | ---: |
  | INT8 | 4036 | 21284 | 415370 |
  | FP8-E4M3 | 14022 | 54564 | 1071252 |
  | FP8-E5M2 | 11742 | 47051 | 924513 |

  These cycles exclude GPU readout/conversion/final arithmetic per the accepted
  boundary. All requests are globally serialized in this minimal frontend.
- Representative deterministic M=1 N=516 physical results equal the scalar
  references: INT8 110, E4M3 raw encoding 0x14, E5M2 raw encoding 0x0A.
  Fixtures and the graph reference are in the focused composition test.
- Generated ADD/MUL operation temporary-row counts are INT8 6/18, E4M3 22/12,
  E5M2 17/7; the macros reserve micro-operation-level maxima of 18, 22 and 17. Every value comes
  from the operation generator. Reproducible JSON/header, layouts and physical
  traces are in `build/pud-gemv/` (generated artifacts, not source authority).
- Final fresh-context audit recovered the canonical .cu, references, Accepted
  decisions, plan and current implementation independently. No correctness
  findings or authority deviations. An additional INT8 M=24 N=4 replay crossed
  a subarray placement boundary successfully (14,688 physical requests).
- Phase-exit evidence: 31 composition checks, 18 frontend checks, 16 focused
  operation-lowerer/API/standalone tests (49 subtests); generated C-header syntax;
  117 local documentation links; whitespace checks including new files and
  `git diff --check`. No broad arithmetic or substrate suite was repeated.
- Integration milestone closed. Static capacity, existing FP8 numerical
  limitations, globally serialized submission and excluded GPU costs are
  documented baseline limits, not newly introduced modeling decisions.
  No commit requested or made.

PuDTrace is a correctness/integration frontend with one request outstanding at
a time. Reported controller cycles are **not the final GEMV performance result**.
Concurrency/dependency-aware trace submission is future work; this milestone
retains serialized submission and unchanged GEMV semantics.

Pre-commit cleanup: explicit `PhysicalRowLayout.temporary_rows` now requires
exactly `additional_temporary_rows`, rejecting insufficient and excess counts.
Live terminology distinguishes PuD micro-operation-level temporary rows from
PuD macro-operation-level temporary rows. Layout schema 2 gives their metadata
fields explicit names. The three regenerated N=516 physical traces are
byte-for-byte unchanged. All 65 directly affected tests (61 subtests) passed;
no C++/wrapper change required a rebuild or wrapper codegen. Local links,
whitespace, and the complete `git diff HEAD` were rechecked before commit review.
