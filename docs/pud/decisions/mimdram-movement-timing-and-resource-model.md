Status: Accepted

Question

What timing histories, shared resources, target transport, and ACT-overhead
treatment realize MIMDRAM-v2 Gate C while retaining the accepted LC/GB local
timing graph, numeric baseline, and recovery boundary?

Decision

**Current status (2026-09-10).** W1-W9 implemented the range-local timing and
resource rules in the canonical
[unified DDR4 PuD substrate](ddr4-pud-unified-substrate.md). T-A resolved-target
consumption is the current transport baseline. Alternative A, Q=8, target
queues, and their verification remain historical provenance only. The
`v2`/`legacy` labels below describe development layers, not runtime models;
the retained LC/GB timing graph and documented fidelity limits remain current.
Acceptance-time statements that public execution was unavailable are
historical.

**Accepted v2 Gate C: timing and target transport, 2026-09-09**

This is the canonical Gate C timing/resource/transport authority, paired with
the [execution and lifecycle authority](mimdram-movement-execution-ownership-and-device.md).
Accepted [Gate A](mimdram-substrate-and-movement-request-boundary.md) fixes the
hybrid claim and unchanged [Gate B](mimdram-addressing-geometry-and-payload.md)
fixes targets. The v2 rules here take precedence over the retained legacy
Bank-conservative/T3 contract below where explicitly refined. No code or
implementation plan is authorized by recording this decision.

The [Accepted mat-target transport abstraction](mimdram-mat-target-transport-abstraction.md)
supersedes only this document's Alternative-A/Q=8 baseline requirements.
This document remains Accepted for all other timing/resource behavior.
The two historical transport subsections below preserve the prior choice and
rationale; they are not current baseline requirements. MIMDRAM's transport
mechanisms and evaluated capacities remain source facts; their mapping to
PRADA and detailed queue semantics were project simulator assumptions.

**History scopes and local timing**

Compute phase history and terminal PRE recovery are range-local. Retain the
[accepted PRADA intervals](pud-timing-resource-and-command-bus-rules.md) and
the current NOT_COPY N-to-ACT_PUD interval; do not duplicate these histories
per mat or impose them through latest-Bank compute history. A range PRE must
not update a Bank-wide deadline that blocks disjoint compute. Bank/rank-wide
work instead waits for all intersecting range recoveries.

Conventional Bank close/autoprecharge and rank PREab/REFab recovery retain
their existing scopes and constrain affected PuD starts. Preserve ordinary
DDR4 timing. Retain the hybrid compute activation-current exclusion as an
explicit assumption; do not infer movement exemptions from PRADA. Keep the
accepted LC/GB local graphs and existing shared constraints below. Enforce
each timing relationship in one authoritative domain, not twice.

**Baseline resolved-target consumption**

Each ACT_PUD* consumes its occurrence's resolved row and MatRange atomically
at issue, under the linked abstraction. There is no modeled physical target
delivery, target FIFO/Q constraint, setup event, successor transport/readiness
state, or mat-target-specific C/A contention. Preserve explicit occurrence
association, range-local timing and ordinary shared command issue constraints.
Omitted transport costs are not physically zero.

**Historical transport Alternative A — Superseded**

The following former baseline is retained as provenance only. Alternative A
was a project mapping onto sequential PRADA activations, not MIMDRAM
terminology or a MIMDRAM-specified PRADA mechanism.

Every ACT_PUD* occurrence consumes its matching precommunicated target before
activation takes effect. Each activation other than the last activation in
that primitive also communicates the next activation's target in the
immediately following C/A cycle. That later activation consumes the prepared
target. N is not an activation; NOT_COPY's queued destination target survives
the intervening N. Identical numerical ranges still require per-activation
communication. This generalizes the source ACT-enqueue/ACT-dequeue behavior
to PRADA; it is not a source-established PRADA command encoding.

| Primitive | Successor target transports, excluding initial setup |
| --- | ---: |
| RowCopy with D destinations | D |
| MAJ3 | 2 |
| MAJ5 | 4 |
| NOT | 0 |
| NOT_COPY | 1 |

For a non-final activation issued at T, reserve C/A at both T (activation)
and T+1 (successor range). The range transmitted at T+1 is available after
that cycle, at T+2 in the integral-cycle convention. The ACT's local phase
starts at T, not T+1. Its transport cycle excludes every other command/event
on the same C/A resource, including unrelated-Bank or movement work, but can
overlap already-running local phase intervals. Check/reserve the next-cycle
bus slot and successor queue credit before issuing the ACT; do not issue an
ACT whose mandatory following transport cannot be honored.

Do not make ACT_PUD* a two-cycle local timing command that shifts accepted
PRADA anchors. Current command_cycles generation adjusts both bus occupancy
and directed-edge offsets; bus reservation and local phase timing must remain
semantically distinct. N and terminal PRE retain one modeled issue cycle and
their own context association; exact physical context-selection encoding is
not claimed.

**Historical initial setup and queue semantics — Superseded**

Use PRE-enqueue when a suitable, legally issued preceding PRE can carry a
known request's target. The PRE uses its existing C/A cycle and applicable
recovery; its close target is distinct from the future target it communicates.
It cannot reset another active range. A historical PRE before the request was
known cannot supply that request's target. Do not insert an otherwise
unnecessary whole-Bank PRE merely to prepare a disjoint range.

Without a suitable PRE, issue one explicit one-CK initial mat-target
setup/transport event before the first ACT. It occupies shared C/A bandwidth
and queue capacity, is ready after that cycle, and changes no DRAM row state.
This is a hybrid simulator event, not a new published DRAM command. Neither
setup nor successor transport advances the architectural primitive cursor.

Retain capacity Q=8 per modeled physical chip, identified through Gate B's
Channel/Rank/Chip context and shared across that chip's Banks/subarrays.
Store only target descriptors, occurrence/context association, readiness,
and occupancy/reservations; no payload values or queue circuitry.

The initial **simulator queue semantics**, not pin-accurate source claims, are:

- Use FIFO descriptor order per chip. A transmission enqueues one descriptor
  on every participating chip, in shared issue order. A descriptor's context
  association is simulator bookkeeping, not an asserted extra wire encoding.
- Check capacity and acquire entries/reservations atomically across the
  participating chips; never partially enqueue or consume a range.
- An ACT requires matching ready head descriptors on every participating chip
  and consumes them atomically. Mismatched heads or absent targets block it.
  N/PRE retain their own context and do not consume a later ACT's descriptor.
- Count reserved successor entries against capacity, allowing the just-consumed
  entries to supply the mandatory following-cycle transmission. Readiness
  probes are pure; no unrelated enqueue may steal that reservation.

Queue pressure and FIFO head blocking are modeled costs. Q bounds outstanding
target information, not active engines: dequeue releases queue space while
the request continues. Engine capacity E=8 and release at terminal recovery
are independently defined by the execution authority. Do not substitute a
blanket min(E,Q) active-request limit or one permanent queue slot per request.

Alternative B (one target load with persistent selection for the whole range
context) is rejected for the initial profile. It is smaller but removes
per-activation communication and requires a different selection extension.

LC/GB retain their accepted transport-fidelity boundary and local timing;
the source does not supply their complete enqueue/dequeue/column-selection
mapping. Do not infer it from this compute hybrid or silently add movement
queue tokens. Compute transports compete with movement occurrences on shared
C/A. This asymmetric fidelity does not claim complete MIMDRAM bus/queue or
movement-throughput accuracy.

The historical transport provisions end here. The ACT-overhead calculation,
local timing and retained movement graph below remain current, with latency
accounting updated for the accepted transport abstraction.

**Fine-grained ACT overhead and latency accounting**

MIMDRAM reports less than 0.5% additional ACT latency from mat isolation
transistors and row-decoder latches; the source and limits are recorded in
the [technical reference](../references/mimdram-inter-column-data-movement.md).
For this hybrid discretization check, apply the 0.5% upper envelope once to
each continuous PRADA ACT-phase interval, then independently ceil by
tCK=0.833 ns. This is a project application of the relative bound, not a
measurement of PRADA/MIMDRAM circuit compatibility or a measured exact 0.5%.

| ACT phase | Existing interval (ns) | 1.005 upper envelope (ns) | Existing CK | Upper-envelope CK |
| --- | ---: | ---: | ---: | ---: |
| A* | 9.000 | 9.045 | 11 | 11 |
| A | 4.000 | 4.020 | 5 | 5 |
| A_S* | 32.992 | 33.156960 | 40 | 40 |
| A_S | 27.992 | 28.131960 | 34 | 34 |

All directed edges using those ACT phases therefore retain their existing
cycle counts. N's 43 CK and PRE recovery's 16 CK are not ACT phases and are
unchanged. Do not scale already-rounded cycles, add a whole CK per ACT, or
inflate the primitive aggregate again. The initial counts absorb this
sub-cycle overhead through current conservative discretization; the hardware
overhead is not physically zero. Recheck this conclusion for another timing
preset or a finer time resolution. This check does not recalibrate movement
or conventional ACT timings.

With resolved targets and no contention, first-ACT-through-terminal-recovery
totals remain RowCopy(D)=40+5D+16 CK, MAJ3=66, MAJ5=76, NOT=99, and
NOT_COPY=104 CK. Range/engine or maintenance waiting and shared command
arbitration can still increase request latency. Distinguish these costs from
local primitive execution and recovery; target-transport latency, mat-queue
stalls and target-delivery-specific C/A contention are omitted under the
linked abstraction, not physically zero. Overlapped costs are not summed
twice; the totals already include terminal nRP. The LC/GB 130/75 CK isolated
local baselines below are
retained, not claims about contended v2 end-to-end latency.

**Retained legacy movement timing contract**

The following describes the existing Bank-conservative executable baseline.
Its movement-local graph remains current; its Bank-serial compute and T3-only
compute transport do not override v2 Gate C above.

Use a primitive-first, Bank-conservative resource abstraction. One range-wide
LC-MOV remains one invocation whose selected mats progress in lockstep; range
length changes payload width but not visible occurrence count or latency. One
singleton GB-MOV remains one invocation with two separately issued,
overlapping physical activation intervals.

Assign all independent requests targeting the same flat Bank to one
conservative conflict domain, including movement, ordinary, and inherited
DDR4_PuD requests. Logical range, chip, mat,
endpoint, and direction metadata remains available for semantics and future
refinement but does not initially permit independent same-Bank concurrency.
Different Banks have no new movement-specific conflict beyond accepted common
controller and DRAM constraints.

Do not initially add a per-mat scoreboard, per-link sidecar, explicit Chip,
Subarray, or Mat timing node, multiple same-Bank movement contexts, a
multi-address Device command, or true same-cycle multi-command issue.
Continuous ownership of this resource domain is defined by
`mimdram-movement-execution-ownership-and-device.md`.

Use T3 mat-information-transport fidelity. MIMDRAM's source defines a
per-chip mat queue and `ACT-enqueue`, `PRE-enqueue`, and `ACT-dequeue`
transport, but the initial simulator does not expose them as movement Device
commands or explicitly model the evaluated eight-entry queue, queue pressure,
transport-specific C/A contention, or resulting cross-Bank/Rank throughput.
This is a scope abstraction, not a zero-cost hardware claim. The technical
reference remains authoritative for the exact source transport mechanism and
its unresolved LC/GB occurrence mapping.
Revisit T3 before modeling command-bus-accurate transport, queue pressure,
same-Bank disjoint-mat MIMD, mat-selective ordinary-command coexistence, or
Device legality/timing/resource behavior that depends on individual mats.

A movement occurrence may issue only when all four conditions hold:

```text
request eligible
prerequisite compatible
primitive-local timing ready
Device timing ready
```

The retained controller primitive-execution context owns relationships whose
meaning depends on primitive type, source/destination role, a particular
earlier occurrence of a repeated semantic command, or another occurrence-
specific condition. It retains the minimum occurrence issue history needed
for those dependencies. Use one localized, generalizable mechanism rather
than scattered LC/GB special cases.

Device timing remains authoritative for context-independent protocol,
resource, and recovery constraints expressible through hierarchy, command
identity, and command history. Primitive-local timing supplements rather than
replaces Device timing. Do not duplicate a constraint across both domains,
add timing-only command aliases, or encode timing readiness in Device state.

A locally timing-blocked occurrence does not reserve the controller or
Channel. Unrelated eligible, timing-ready work in other Banks remains
selectable under existing arbitration and shared constraints. Primitive-local
readiness therefore participates in scheduler candidate readiness and final
pre-issue validation.

Use the project `DDR4_2400R` combined-substrate baseline:

```text
tCK  = 833 ps
nRCD = 16 CK
nRTP = 9 CK
nRAS = 39 CK
nRP  = 16 CK
nWR  = 18 CK
```

These are project values inherited from the selected Ramulator2 preset, not
a claim that MIMDRAM evaluated the identical component-timing tuple or
`2400R` speed-bin suffix.

Adopt FIGARO's guarded value as an explicit simulator assumption:

```text
tRELOC = 1 ns
nRELOC = ceil(1000 ps / 833 ps) = 2 CK
```

FIGARO provides primary-source evidence for a related relocation mechanism,
but does not directly validate MIMDRAM's exact LC local path or GB
neighboring-global-SA path. Applying this value to both is a project choice.
Quantize every independently enforced continuous interval independently:

```text
nX = ceil(tX / tCK)
```

For LC, `nRELOC + nWR = 2 + 18 = 20 CK`; do not re-quantize a rounded
aggregate.

Use these LC primitive-local dependencies:

| Predecessor | Following occurrence | Delay |
| --- | --- | ---: |
| occurrence 0 `ACT_MOV(source)` | occurrence 1 `RD_MOV(source)` | `nRCD = 16 CK` |
| occurrence 1 `RD_MOV(source)` | occurrence 2 source `PREpb` | `nRTP = 9 CK` |
| occurrence 4 `WR_MOV(destination)` | occurrence 5 terminal `PREpb` | `nRELOC + nWR = 20 CK` |

The first two edges adopt the source phase's regular `ACT-RD-PRE` readiness
structure without importing ordinary external-DQ timing into `RD_MOV`.
Retaining the HFF payload across source PRE adds no source-side relocation
delay in this accepted graph.

Use these context-independent LC Device relationships:

```text
latest target-Bank ACT_MOV -> PREpb  = nRAS = 39 CK
latest target-Bank ACT_MOV -> WR_MOV = nRAS = 39 CK
PREpb -> ACT_MOV                     = nRP  = 16 CK
```

The latest-`ACT_MOV` edges use history window 1. They constrain source PRE
from source ACT, and destination WR and terminal PRE from destination ACT.
Waiting for destination ACT plus `nRAS` before LC destination WR is an
explicit conservative simulator decision.

The isolated LC issue/recovery timeline is:

| Cycle | Occurrence | Controlling readiness |
| ---: | --- | --- |
| 0 | `ACT_MOV(source)` | start |
| 16 | `RD_MOV(source)` | source ACT + `nRCD` |
| 39 | source `PREpb` | `max(source ACT+nRAS, RD+nRTP)` |
| 55 | `ACT_MOV(destination)` | source PRE + `nRP` |
| 94 | `WR_MOV(destination)` | destination ACT + `nRAS` |
| 114 | terminal `PREpb` | `max(destination ACT+nRAS, WR+nRELOC+nWR)` |
| 130 | recovery complete | terminal PRE + `nRP` |

Therefore:

```text
T_LC,sim = 2 * (nRAS + nRP) + nRELOC + nWR = 130 CK
```

MIMDRAM's source equation is `2*(tRAS+tRP)+tRELOC+tWR`. The chosen
post-`WR_MOV` placement of `tRELOC` and serialization of `nRELOC+nWR` are
project modeling choices, not source-stated directed edges. They causally
associate relocation with the WR-established destination path and reproduce
the conservative critical-path structure.

Use these GB primitive-local dependencies:

| Predecessor | Following occurrence | Delay |
| --- | --- | ---: |
| occurrence 0 source `ACT_MOV` | occurrence 2 `RD_MOV(source)` | `nRAS = 39 CK` |
| occurrence 2 `RD_MOV(source)` | occurrence 3 `WR_MOV(destination)` | `nRELOC = 2 CK` |
| occurrence 3 `WR_MOV(destination)` | occurrence 4 terminal `PREpb` | `nWR = 18 CK` |

The source-RD dependency explicitly uses source ACT occurrence 0 even after
destination ACT occurrence 1 has issued. Use these context-independent GB
Device relationships:

```text
latest target-Bank ACT_MOV -> WR_MOV = nRAS = 39 CK
latest target-Bank ACT_MOV -> PREpb  = nRAS = 39 CK
PREpb -> later opening               = nRP  = 16 CK
```

For GB, the latest ACT is the destination occurrence. Preserve both visible
ACT occurrences and at most one issue per simulator tick without claiming
that MIMDRAM physically uses successive C/A cycles.

The isolated GB issue/recovery timeline is:

| Cycle | Occurrence | Controlling readiness |
| ---: | --- | --- |
| 0 | `ACT_MOV(source)` | start |
| 1 | `ACT_MOV(destination)` | next simulator issue slot |
| 39 | `RD_MOV(source)` | source ACT occurrence 0 + `nRAS` |
| 41 | `WR_MOV(destination)` | `max(RD+nRELOC, destination ACT+nRAS)` |
| 59 | terminal `PREpb` | `max(WR+nWR, destination ACT+nRAS)` |
| 75 | recovery complete | terminal PRE + `nRP` |

Explicitly, destination `ACT_MOV + nRAS = 1 + 39 = 40`, while source
`RD_MOV + nRELOC = 39 + 2 = 41`. The relocation dependency naturally hides
the one-CK simulator issue offset. No cycle is subtracted or ignored, and no
timing alias is introduced.

Therefore:

```text
T_GB,sim = nRAS + nRELOC + nWR + nRP = 75 CK
```

MIMDRAM's source equation is `tRAS+tRELOC+tWR+tRP`. The accepted
`RD_MOV(source) -> WR_MOV(destination) = nRELOC` edge is a simulator
decomposition of that aggregate equation, not a source-stated directed edge.
The exact physical GB C/A issue relationship remains unknown.

Retain context-independent inherited recovery into the first `ACT_MOV`:

```text
PREpb -> ACT_MOV = nRP
PREab -> ACT_MOV = nRP
RDA   -> ACT_MOV = nRTP + nRP
WRA   -> ACT_MOV = nCWL + nBL + nWR + nRP
REFab -> ACT_MOV = nRFC
```

Terminal `PREpb` imposes ordinary `nRP` recovery before a later ordinary ACT,
inherited DDR4_PuD opening command, another `ACT_MOV`, or `REFab` as
applicable. Source LC `PREpb -> destination ACT_MOV` is an instance of that
general rule.

Interpret the published MIMDRAM latency equations as first movement
activation through completion of terminal precharge recovery because both
include terminal `tRP`. Keep three boundaries distinct:

```text
first ACT_MOV -> terminal PREpb issue
    visible sequence and ownership/state-cleanup boundary

first ACT_MOV -> terminal PREpb recovery completion
    published-equation comparison boundary

request depart/callback/statistics completion
    request lifecycle uses terminal recovery; statistics remain a later gate
```

When terminal `PREpb` issues at cycle `T`, Device state becomes `Closed`,
movement ownership ends, and the request leaves active/schedulable controller
state. Retain the retired request in the shared delayed-completion path with
`depart = T + nRP`. At cycle `T + nRP`, terminal recovery is complete; extract
and erase the pending completion before invoking its callback exactly once.
This lifecycle boundary does not define movement-specific statistics or
modeled data availability.

Initially add no movement-specific `tRRD`, `tFAW`, activation-current rule,
ordinary same-Bank `nRC` constraint between the two GB activations, external
RD/WR burst/CAS/DQ-turnaround or sibling-rank DQ timing, or undocumented
Rank/Channel movement-datapath constraint. Each omission is a fidelity
limitation, not a physical exemption.

Implementation impact is limited by the accepted architecture: primitive-
local timing must participate in scheduler candidate readiness and final
issue validation, while context-independent edges remain in Device timing.
The exact context fields and API are implementation choices. Existing
DDR4_PuD primitives need not migrate to the localized mechanism unless a
later implementation audit finds that generalization beneficial.

Rationale

For v2, one history per active range preserves local PRADA timing. The current
transport abstraction's rationale is in its linked Accepted decision.
The following is the historical rationale for the superseded transport choice:
Alternative A exposes C/A and
finite queue costs using source-inspired overlap instead of either silently
zero-cost targeting or a persistent-selection extension. Explicit setup
handles cold/late arrivals without inventing a historical PRE payload. The
rounding calculation preserves the reported hardware-overhead boundary without
adding unsupported integral-cycle penalties. FIFO/atomic queue rules are
simulator choices necessary for coherent multi-engine consumption.

The rationale below explains the retained legacy movement graph and omissions.

The conservative Bank domain avoids unsupported precision about movement-
specific mat/link conflicts while retaining existing different-Bank
parallelism. T3 avoids inventing an LC/GB enqueue/dequeue schedule that the
source does not provide.

Splitting timing responsibility lets static Device history enforce general
resource/recovery rules while the retained context selects particular
occurrences, especially GB's source ACT after the destination ACT becomes the
latest Device history entry. It preserves shared semantic IDs and allows
other Banks to progress during local timing gaps.

The directed graphs retain every visible occurrence and independently
quantized interval while reproducing the two accepted conservative source-
equation structures. Explicit evidence labels prevent the FIGARO calibration
and LC/GB decompositions from being mistaken for direct MIMDRAM circuit facts.

Evidence

Gate C was accepted by the user on 2026-09-09. The curated reference records
MIMDRAM source facts from section 4.2, section 7, and Table 2: enqueue/dequeue,
overlap, per-chip queue, evaluated resources, and fine-grained ACT overhead.
The PRADA mapping, cold-start event and exact FIFO/atomic synchronization were
accepted project assumptions, now superseded as baseline requirements by the
linked abstraction. The relative-bound application remains Accepted.

Current implementation facts: [Python timing generation](../../../python/ramulator/dram/spec.py)
adjusts edge anchors for multi-cycle commands; [compute timing](../../../python/ramulator/dram/ddr4_pud.py)
uses Bank histories; [movement occurrence timing](../../../src/ramulator/controller/pud_sequence.cpp)
already supplements Device timing. Existing [compute](../../../tests/device_timings/test_ddr4_pud.py)
and [movement](../../../tests/controller_scheduling/GenericDDRController/test_movement_local_timing.py)
tests assert legacy intervals, not v2 transport or independence. Decimal
arithmetic verified the four upper-envelope ceiling results above during
acceptance; no runtime simulator tests were run for this documentation change.

`docs/pud/references/mimdram-inter-column-data-movement.md` is authoritative
for MIMDRAM's aggregate LC/GB equations, overlapping GB activation intervals,
physical movement paths, mat queue and transport commands, unresolved exact
GB C/A relation, and FIGARO's raw and guarded relocation evidence. The Bank
resource domain, T3 abstraction, timing-domain split, selected baseline,
application of `tRELOC`, directed-edge placements, and initial omissions are
project simulator decisions.

Repository evidence is the `DDR4_2400R` preset, hierarchy command-history
timing, issue-time timing/action updates, retained primitive context,
one-command-per-tick controller behavior, scheduler readiness path, and
existing general PRE/refresh recovery edges.

This document consolidates the current accepted authority formerly carried by
`mimdram-movement-timing-resource-scope.md`,
`mimdram-movement-timing-responsibility.md`,
`mimdram-movement-numeric-timing-and-directed-edges.md`, and the T3 transport
portion of `mimdram-mat-targeting-and-transport-abstraction.md`. Those files
remain as historical provenance.

Open issues

- Physical validation or future refinement of the selected LC/GB `tRELOC`
  placement, LC relocation/write serialization, and GB directed decomposition.
- Physical movement command encoding and exact C/A-bus occupancy.
- Whether stronger evidence requires movement `tRRD`, `tFAW`, activation-
  current, ordinary row-cycle, DQ, or additional shared Rank/Channel rules.
- Physical validation of the historical hybrid transport encoding and
  FIFO/atomic queue semantics if revisited for optional sensitivity analysis;
  these are not baseline implementation prerequisites. More detailed movement
  transport remains outside this profile.
- Portability of the numeric assumptions to another timing preset,
  organization, or DRAM standard.
- Current implementation progress is recorded in the
  [implementation plan](../plans/mimdram-pud-substrate-v2-implementation-plan.md).
