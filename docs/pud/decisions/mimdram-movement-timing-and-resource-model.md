Status: Accepted

Question

What timing/resource abstraction, mat-information-transport fidelity,
directed timing graph, numeric baseline, and latency boundary should the
initial LC-MOV and GB-MOV model use?

Decision

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
    later lifecycle gate
```

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
- A future T1/T2 model of mat-transport queue pressure and contention.
- Portability of the numeric assumptions to another timing preset,
  organization, or DRAM standard.
- Future finer-grained same-Bank MIMD resource and timing fidelity.
