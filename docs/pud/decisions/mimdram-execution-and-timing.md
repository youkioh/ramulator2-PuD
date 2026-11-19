Status: Accepted

Question

What experiment boundary, request boundary, execution state, ownership,
lifecycle, maintenance interaction, target transport, timing, and statistics
govern mat-scoped PRADA compute and MIMDRAM LC-MOV/GB-MOV movement in the
canonical PuD substrate?

Decision

This is the canonical execution, timing, and lifecycle authority for the
[unified DDR4 PuD substrate](ddr4-pud-unified-substrate.md). Locations,
footprints, payload, and compute effects are fixed by the
[geometry and placement decision](mimdram-geometry-and-placement.md). The
[multistandard decision](pud-multistandard-substrate.md) reuses this model
for GDDR7 and HBM3 and owns their standard-specific bindings. All rules below
are Accepted project decisions, not assertions of physical equivalence to
MIMDRAM; source facts are identified in Evidence and in the linked references.

**Experiment and hybrid boundary**

The substrate is an experimental PRADA/MIMDRAM hybrid supporting functional
mat-scoped computation and LC/GB movement under the accepted placement, with
independent same-Bank execution on disjoint physical mat footprints. It
supports architectural timing experiments under declared assumptions, not
physical equivalence to either complete design or reproduction of MIMDRAM's
published end-to-end performance.

Source facts: the curated PRADA references describe RowCopy, MAJ3, MAJ5,
NOT, and NOT-and-copy; MIMDRAM describes mat selection, independent execution,
and LC/GB movement. The supplied sources do not establish that MIMDRAM
physically validates PRADA's complete circuit/timing model unchanged.

Hybrid assumption: apply all five PRADA mechanisms and the pointwise compute
effects of the geometry decision to its explicitly selected mat-rows,
including destructive majority and NOT behavior. Support majority only with
distinct physical-row operands; repeated-row charge-sharing semantics are
unsupported. Unselected locations remain preserved.

Retain the PRADA-derived compute phase decomposition, including the assumed
`tCS`, derived sensing/restoration interval, and independently rounded timing
intervals ([compute timing decision](pud-timing-resource-and-command-bus-rules.md)).
Local compute phase costs are independent of selected mat-range width; retain
the existing incremental cost per RowCopy destination and do not invent
width-dependent compute timing. Distinguish:

```text
local PRADA-derived compute phase cost
    +
substrate scheduling / shared-resource overhead
```

Inputs may already be allocated, initialized, bitsliced, and placed according
to the geometry decision. Allocator, compiler, transposition machinery, full
ISA integration, the full INT8/FP8/GEMV macro library, and their costs are
outside substrate scope.

Once implemented and validated, supported claims are functional correctness
of mat-scoped operations and explicit compositions, modeled primitive latency,
same-Bank overlap on supported disjoint resources, and reduction timing under
the declared placement/movement/resource model. Implementation and
validation status is recorded in the completed plans cited in Evidence.

Unsupported claims include complete MIMDRAM throughput or end-to-end GEMV
speedup, physically exact mat-transport/C/A occupancy or queue saturation,
fully validated local/global-I/O contention, activation-current constraints,
refresh-retention guarantees, unchanged hybrid circuit compatibility,
physical reliability, energy, or area. Conservative project choices do not
make total predicted performance a proven physical lower bound: omitted costs
can bias results in the opposite direction. Omitted transport and movement
timing effects are evidence limits, not physical zero-cost or
resource-exemption claims.

**Request boundary**

Represent LC-MOV and GB-MOV as distinct architectural request types. One
submitted request is one LC-MOV or one GB-MOV invocation. The controller owns
the request lifecycle and the sequencing boundary for its visible occurrences.
Movement-specific addressing, state, ownership, and timing choices do not
retroactively become PRADA properties; the inherited RowCopy, MAJ3, MAJ5,
NOT, and NOT_COPY semantics are unchanged by movement support.

One request excludes ISA-level `bbop_mov` lowering, array placement, a batch
of movement invocations, multi-invocation orchestration, vector-reduction
orchestration, automatic multi-hop routing, a software frontend, and the full
MIMDRAM control stack. Those mechanisms may later construct or coordinate
LC-MOV/GB-MOV requests but are not part of one architectural request.

Reuse shared request, controller, scheduler, Device, and completion
infrastructure only where their abstractions fit. Do not infer movement
placement, timing/resource, ownership, state, or maintenance semantics from
inherited PRADA-only behavior.

**Connectivity**

LC copies locally across its selected lockstep range; GB uses singleton
directed local-mat neighbors `i-1 -> i` within one chip and derived subarray.
A chip-crossing LC range does not transfer data across chips. Arbitrary
non-neighbor or reverse GB, wrapping, cross-chip movement, wider GB endpoint
ranges, and automatic multihop routing are unsupported. A supplied stream may
compose legal operations with explicit temporary rows and dependencies; the
substrate promises neither arbitrary endpoint reachability nor routing.

**Reduction and host completion**

Source fact: MIMDRAM describes inter-mat GB-MOV + ADD followed by an intra-mat
LC-MOV + ADD tree reducing to four residual elements. Movement counts depend
on precision; four transferred bits are not four complete arbitrary-precision
elements. The curated source supplies no subsequent 4-to-1 mechanism.

The substrate provides mat-scoped compute, GB-MOV, LC-MOV, and
dependency-safe request execution/completion sufficient to express that path.
The concrete ADD primitive sequence, temporary-row placement,
precision-specific movement counts, arithmetic policy, and complete reduction
request stream belong to the operation/macro layer
([GEMV/GEMM workload decision](pud-gemv-gemm-workload.md)). Neither an INT/FP ADD
implementation nor a reduction macro is a substrate requirement. A concrete
macro's correctness and timing require its precision, temporary-row use, legal
movements, and dependencies to be specified; the substrate itself supplies no
reduction latency or request count.

Completion boundary: four residuals per legally reduced domain, with all
remaining combination performed by the host. Where supported connectivity
cannot merge contributions, retain separate partial outputs for host
combination rather than claiming four residuals for the whole workload. No
cross-position shuffle or all-in-DRAM scalar reduction is provided.
Substrate reduction timing ends after recovery of its final required
primitive. Host readout, representation conversion, and remaining arithmetic
require separate accounting before claiming scalar-result latency.

**Range contexts and compute temporal state**

Use one temporal execution context per allocated lockstep compute range or
acquired movement invocation. Derive mat availability from protected
active/recovering range records; independent full state per mat and a
replica of the physical scoreboard are unnecessary. Retain each range's
resolved identity, operand/activated-row context, phase, occurrence progress,
and local timing history. Controller sequencing owns primitive identity,
operand ordering, and the next occurrence; Device legality must distinguish
independent range phases.

Keep conventional Bank row state separate. Every activation, N, and close
must retain its own resolved target/context; another range's command must not
overwrite that association. A Bank-global last-selected-range variable is
insufficient. The geometry decision selects locations; this decision selects
temporal effects.

| Compute occurrence | Effect within its selected range only |
| --- | --- |
| First ACT_PUD_OC | Establish first operand activation; enter PuDChargeSharing. |
| ACT_PUD while charge sharing | Add intended operand activation; remain unsensed. |
| ACT_PUD_S | Add final majority operand and enter PuDSensed. |
| First ACT_PUD_S_OC | Establish source activation and enter PuDSensed. |
| ACT_PUD while sensed | Add intended copy-destination activation; remain sensed. |
| N | Remain sensed with the source activation retained; inversion has no stored bit values here. |
| Terminal compute PRE | Close this invocation's activated rows across its range; discard its active sensing/row context and begin range-local recovery. |

Preserve the five accepted primitive sequences and their exact controller
ordering. N remains aggregate. Charge-sharing PRE, premature terminal PRE,
abort, preemption, and save/resume are unsupported. Retain PREpb as a semantic
identity with explicit effective close scope: compute terminal PRE is
range-local; ordinary PRE remains Bank-wide. Coarse BankTarget metadata alone
cannot select its state or timing effect. Closing A cannot close/reset B.

**Footprints, conflicts, and admission**

Every PuD invocation exclusively protects its physical mat footprint: compute
and LC use the selected MatRange; GB uses the union of its resolved source and
destination singleton endpoints. Derive chip/local-mat segments through the
retained resolver, ignoring operand rows and columns for resource
intersection. Do not duplicate placement formulas or invent additional GB
topology. Disjointness is evaluated in the full resolved context (Channel,
Rank, BankGroup, Bank, Subarray, Chip, Mat), not by comparing bare logical mat
numbers from different subarrays or Banks.

```text
PuD conflict scope = physical mat-footprint intersection
                   + separately modeled shared command/timing constraints
```

All six compute/LC/GB pair classes permit concurrent progress on disjoint
footprints within the same legal subarray; intersections serialize through
recovery, even when operand rows differ. Do not start PuD work in a different
subarray of the same Bank until all protected contexts there, including
recovery, drain; SALP is not implicit in distinct CellIDs. Different Banks may
progress subject to shared issue, maintenance, and applicable timing.

Overlap means independent execution progress, not merely simultaneous
admission. At least two independent compute requests on disjoint ranges in
one subarray must be able to overlap while preserving independent state, data,
and recovery; one range's close or recovery must not reset another. Shared
command issue and legitimate shared constraints still apply; same-cycle
multi-command issue and linear speedup are not required. Validation must cover
same-operation overlap and at least one heterogeneous overlap case.

Compute primitives and LC-MOV/GB-MOV have no finite control-engine charge
(see **No finite control-engine capacity** below).
Scan pending compute oldest-to-newest using online first fit: allocate the
first request whose complete range is available, subject to ordinary/movement,
subarray, and maintenance eligibility. Allocation is distinct from command
arbitration and local timing readiness. Reserve the complete physical range
atomically on allocation, including any pre-first-ACT wait for normal
arbitration or local timing. An unallocated pending request owns nothing.
Retain request-count pending buffering; do not reproduce the 2 kB bbop-buffer
hardware.

Movement acquires its complete footprint atomically with first ACT_MOV, owns
nothing before that issue (including preparatory ordinary PRE), and retains
protection through terminal PRE+nRP. Failed admission is retryable without
partial ownership. A per-invocation context replaces Bank movement state; the
Request remains the sole cursor/history and endpoint authority.

Ordinary Device-issued ACT/RD/WR/RDA/WRA and unrelated Bank PRE conflict with
protected same-Bank PuD contexts. Existing ordinary activity must drain and
conventional close/recovery must complete before PuD allocation or movement
acquisition. A preparatory ordinary PRE does not acquire a footprint or advance
a PuD occurrence cursor; another request may reopen the conventional Bank
before acquisition, requiring another preparatory PRE.

Eligibility applies before prerequisites and again before issue, including
complete maintenance/plugin scopes. Preserve active-continuation precedence,
FIFO priority-head blocking, promotion-backpressure handling, and existing
ordinary/movement command arbitration; compute allocation uses the first-fit
policy above. Timing-blocked contexts do not monopolize shared command issue.
Ordinary ACT/RD/WR/RDA/WRA, unrelated PRE, PREab, and refresh cannot interrupt
any protected context within their complete scope. Device rejection is
defensive protection before timing or state mutation. Independent PuD
occurrences instead use their associated invocation and footprint checks.

**No finite control-engine capacity**

This common policy applies to DDR4, GDDR7 and HBM3 PuD. The modeled path is
logical PuD operation -> physical PuD primitives -> DRAM command sequences.
Model physical hierarchy/placement, mat/subarray/Bank footprints and
conflicts, command resources and timing, no-SALP where applicable, movement
dependencies, conventional/PuD protection, terminal recovery,
frontend/dependency ordering and independently modeled queue/resource limits.

Finite SIMDRAM/MIMDRAM bbop/microProgram control-unit throughput capacity is
**outside the performance abstraction**. RowCopy, MAJ3, MAJ5, NOT, NOT_COPY,
LC-MOV and GB-MOV have **no finite control-engine charge**. There is no
primitive engine count and no engine-pool scope. Do not impose E=8 or any
other finite E as a runtime primitive concurrency limit, multiply E by Banks,
or create per-Bank pools. This omits a bottleneck; it does not assert infinite
physical hardware resources. MIMDRAM's reported eight engines remain prior-work
architecture/area evidence, not this simulator's primitive performance
parameter.

Do not introduce parent ADD/MUL/movement contexts, bbop IDs, OPERATION
directives, completion joins or cross-output GEMV grouping merely to retain E.
The investigated parent-context model is rejected. Existing arithmetic
lowering, GEMV calls, reduction ordering, physical traces and CHAIN dependency
semantics continue without bbop engine identity. Target trace/hierarchy
representation (G5) and GEMV placement/mapping portability (G7) do not depend
on finite-engine modeling. Physical footprint ownership/conflicts, no-SALP,
command and movement timing, placement, arithmetic/GEMV dependencies, terminal
recovery and conventional/PuD protection are unaffected by this policy.
Completed older plans and the original source audit describe the former
finite-engine implementation; they do not restore engine authority.

Reintroducing finite engines requires a **new explicit architecture/modeling
decision** and a dedicated audit of SIMDRAM, MIMDRAM, Proteus and later
architectures explicitly modeling the same bottleneck. For each relevant work,
independently establish:

1. What consumes a context: bbop, complete operation, primitive, partition or other entity?
2. Its scope: controller, Channel, Rank, Bank, subarray or another unit.
3. The number of contexts.
4. The allocation event.
5. The release event.
6. Whether movement consumes the same resource.
7. Interaction with BLP.
8. Interaction with SALP.
9. Whether one context controls multiple Banks/subarrays.
10. The actual hardware/control mechanism enabling any such fan-out.
11. Whether independent operations progress concurrently.
12. Whether the performance simulator implements finite occupancy/backpressure.
13. Whether engines appear only in architectural prose or area accounting.
14. How published performance evaluation accounts for capacity.
15. The public source/code supporting each claim.

Expose ambiguity, missing mechanisms, architecture/evaluation inconsistencies
and unavailable implementation details; do not repair them silently. If no
complete prior-work model is recoverable, label any proposed finite model
**NEW PROJECT MODELING ASSUMPTION**, not “MIMDRAM engine model.” Evaluation
must justify, and preferably sensitivity-sweep, count, scope, allocation
granularity, release lifetime, movement accounting and BLP/SALP interaction.
Eight reported engines alone cannot restore E=8. E×Banks, one engine per
primitive/Bank, or arbitrary multi-Bank parent control are forbidden shortcuts
unless a new audit independently establishes that exact behavior.

**Recovery, maintenance, and completion**

At terminal PRE issue T, remove the sequence from command scheduling but
retain its footprint protection. At T+nRP:

```text
release footprint protection
complete request/accounting and invoke callback exactly once
```

Use the shared delayed-completion mechanism. Extract/erase a ready completion
before callback; preserve departure reordering and reentrant submission
safety. Recovery does not reset another context.

Queued priority maintenance stops new allocations through the retained
priority policy; already allocated contexts drain without interruption.
PREab/refresh waits for every intersecting context and its recovery, with
whole-scope validation before mutation. Issue conventional PREab only when
required by remaining ordinary row state, then honor its recovery.
Already-active maintenance prevents affected starts until its applicable
timing expires. Use the F-A refresh policy inherited from GenericDDR: a queued
priority refresh prevents a pending movement from acquiring ownership; a
refresh generated after acquisition waits for the non-preemptive invocation
and its protected recovery before REFab. Add no refresh deadline admission,
deferral credit, retention guarantee, pause/resume, or scope-aware priority
bypass; this is an inherited fidelity limitation, not a physical guarantee.

Dependent macro operations must wait for all required producer completions,
including destructive-operand/temporary-row reuse. Submission order and
conflict exclusion alone do not establish dependencies. No dependency-graph
scheduler or earliest electrical data-visibility claim is introduced.

**Timing/functional split**

Ramulator stores no DRAM, SA, compute-working, or HFF payload values and has
no staged functional commit. The same request and canonical resolver feed the
timing/state model and a separate PuD functional simulator. Actual values for
all five compute primitives and LC/GB belong to that functional simulator; the
timing callback establishes completion ordering, not a bit-storage API. Do not
modify ordinary forwarding/coalescing or add ordinary RD/WR value simulation.
Host/cache coherence and mixed ordinary/PuD functional coherence are outside
this contract.

**Movement sequences and command identities**

Keep LC-MOV and GB-MOV as controller-sequenced request-level operations with
these Ramulator-visible occurrences and potential timing boundaries:

```text
LC-MOV:
ACT_MOV(source)
-> RD_MOV(source)
-> PREpb
-> ACT_MOV(destination)
-> WR_MOV(destination)
-> PREpb

GB-MOV:
ACT_MOV(source)
-> ACT_MOV(destination)
-> RD_MOV(source)
-> WR_MOV(destination)
-> PREpb
```

Use exactly three semantic movement command identities: `ACT_MOV`, `RD_MOV`,
and `WR_MOV`; reuse existing `PREpb`. The names are simulator identities, not
names claimed by MIMDRAM. Source/destination, LC/GB, and position are
occurrence roles, not distinct command types. Do not add source/destination or
LC/GB variants, a movement-specific PRE, generic `CLOSE`, or timing-only
aliases. `ACT_PUD`, `ACT_PUD_OC`, `ACT_PUD_S`, and `ACT_PUD_S_OC` remain
PRADA-specific and are not reused. Ordinary `ACT`, `RD`, and `WR` are not
reused because their flat-Bank, row-hit, host-DQ, row-policy, and statistics
meanings do not apply to internal movement occurrences.

Set `is_opening=false`, `is_accessing=false`, and `is_closing=false` for all
three movement commands, each with `BankTarget::Single`. These fields classify
controller, row-policy, and plugin behaviors; they do not describe every
physical action. Movement activation therefore does not enter the generic
active-buffer path or activation-based RowHammer handling, and movement
transfer phases are not row-buffer accesses. Provide no movement `rowhit` or
`rowopen` handlers. Keep shared `PREpb` metadata and its single-Bank target.

The retained request/controller execution context owns primitive identity,
the two ordered operands, resolved endpoint metadata, one monotonic occurrence
cursor, each occurrence's role, and the occurrence issue history required by
primitive-local timing. The cursor advances only when the intended
architectural occurrence issues. A preparatory prerequisite neither advances
the cursor nor substitutes, skips, or reorders an occurrence.

**Movement Device states**

The invocation's Device phase is MovementActive or MovementDataValid during
the sequence and Recovering after terminal PRE. These are simulator validity
markers, not physical circuit states or payload storage. Request history
derives source/destination activation and source-valid metadata; no duplicate
cursor, per-mat phase, stored HFF value, or global-SA/link state is introduced.

| Occurrence | Effect only on its invocation |
| --- | --- |
| First ACT_MOV | Closed → MovementActive; acquire the entire footprint. |
| Later ACT_MOV | Retain current phase; activate the intended endpoint. |
| RD_MOV | MovementActive → MovementDataValid. |
| LC source PRE | Retain MovementDataValid; close source activation only. |
| LC destination ACT | Retain source validity across source recovery. |
| WR_MOV | Consume source validity; enter MovementActive. |
| Terminal PRE | Close LC destination or both GB endpoints; enter Recovering. |
| Terminal PRE+nRP | Release footprint; complete Request once. |

The validated occurrence selects PRE scope, not BankTarget metadata or another
invocation's state. Movement never populates or changes conventional row
state. These close scopes are simulator refinements; exact physical
mat-selective PRE wiring is outside the modeled claim. Source PRE, terminal
PRE, and recovery cannot reset or block a disjoint PuD context except through
a separately modeled shared constraint.

**Row policies, plugins, and traces**

The Open and ClosedCAP row policies require no movement-specific behavior.
ClosedCAP's exact `RD`/`WR` upgrade checks cannot convert movement to
`RDA`/`WRA`, and movement's non-accessing metadata cannot increment its CAP or
trigger policy-generated PRE. Shared movement `PREpb` notifications may retain
the existing close-bookkeeping path, which is behaviorally inert because
movement enters ownership from an already-Closed Bank or after a preparatory
conventional `PREpb`, and no movement occurrence increments the CAP.
Ownership remains the protection against independently queued policy work.

Pure observational controller plugins may observe issued movement commands;
this is command visibility only, not functional movement-data knowledge. Keep
the `CmdTraceRecorder`, `BinTraceRecorder`, and `LiveTraceStreamer` schemas
and lifecycle interfaces unchanged: command identity, issue cycle, request
type, source ID, and occurrence address make movement visible, and tracing
assigns the address's Column coordinate no additional physical meaning.
RAM2BIN and live events also retain their existing arrival field. The
fixed sequence may identify occurrence roles in an isolated directed trace,
but the schemas have no unique request identity and are not
request-reconstruction formats. Do not add logical-mat metadata, moved bits,
occurrence role/index or history, or delayed departure/callback events to
production traces.

Plugins already incompatible because the standard lacks required VRR or RFM
capabilities remain rejected by their setup checks. Reject AQUA and RRS at
setup whenever the DRAM standard is movement-capable: their RIT
placement/remapping semantics are not functionally integrated with movement
operands.

**Target transport**

Every PuD request/occurrence retains its resolved target metadata. The Device
consumes the corresponding row and resolved `MatRange` atomically when
`ACT_PUD*` issues:

```text
Request / PuDOccurrence
    row + resolved MatRange
         |
         v
    ACT_PUD* Device action
```

This models the selected-mat effect and abstracts physical delivery of the
selection. It is a simulation abstraction, not a new DRAM command, hardware
design, or claim that DDR4 can encode the range on the same C/A pins in the
ordinary ACT cycle. Each compute occurrence, including N and PRE, keeps its
explicit range/context association; there is no Bank-global or implicitly
persistent selection.

The model excludes per-chip mat-information FIFO occupancy, Q=8 as a
performance/resource constraint, ACT-enqueue/PRE-enqueue/ACT-dequeue
execution, per-activation target-descriptor preparation, target-transport and
readiness events, target-only setup events, and mat-target-specific C/A
contention. Ordinary command issue arbitration and applicable shared timing
remain modeled.

For LC/GB, MIMDRAM's per-chip mat queue and `ACT-enqueue`, `PRE-enqueue`, and
`ACT-dequeue` transport are likewise not exposed as movement Device commands;
the evaluated eight-entry queue, queue pressure, transport-specific C/A
contention, and resulting cross-Bank/Rank throughput are not modeled. Do not
infer an LC/GB enqueue/dequeue schedule that the source does not provide.

**Fidelity limitation.** Results do not include mat-information transport
latency, mat-queue occupancy stalls, or C/A contention caused specifically by
mat-information delivery. These effects are omitted, not physically zero.
Report this limitation with results; do not claim physically complete MIMDRAM
target-transport performance. Revisit it for command-bus-accurate target
transport, queue pressure, or mat-selective ordinary-command coexistence.

**Compute timing scopes and ACT overhead**

Compute phase history and terminal PRE recovery are range-local. Retain the
[accepted PRADA intervals](pud-timing-resource-and-command-bus-rules.md) and
the NOT_COPY N-to-ACT_PUD interval; do not duplicate these histories per mat
or impose them through latest-Bank compute history. A range PRE must not
update a Bank-wide deadline that blocks disjoint work. Bank/rank-wide work
instead waits for all intersecting range recoveries.

Conventional Bank close/autoprecharge and rank PREab/REFab recovery retain
their existing scopes and constrain affected PuD starts. Preserve ordinary
DDR4 timing. Retain the hybrid compute activation-current exclusion as an
explicit assumption; do not infer movement exemptions from PRADA. Enforce each
timing relationship in one authoritative domain, not twice.

MIMDRAM reports less than 0.5% additional ACT latency from mat isolation
transistors and row-decoder latches. Apply the 0.5% upper envelope once to
each continuous PRADA ACT-phase interval, then independently ceil by
tCK=0.833 ns. This is a project application of the relative bound, not a
measurement of PRADA/MIMDRAM circuit compatibility or a measured exact 0.5%.

| ACT phase | Existing interval (ns) | 1.005 upper envelope (ns) | Existing CK | Upper-envelope CK |
| --- | ---: | ---: | ---: | ---: |
| A* | 9.000 | 9.045 | 11 | 11 |
| A | 4.000 | 4.020 | 5 | 5 |
| A_S* | 32.992 | 33.156960 | 40 | 40 |
| A_S | 27.992 | 28.131960 | 34 | 34 |

All directed edges using those ACT phases retain their existing cycle counts.
N's 43 CK and PRE recovery's 16 CK are not ACT phases and are unchanged. Do
not scale already-rounded cycles, add a whole CK per ACT, or inflate the
primitive aggregate again. The counts absorb this sub-cycle overhead through
conservative discretization; the hardware overhead is not physically zero.
Recheck for another timing preset or finer time resolution. This check does
not recalibrate movement or conventional ACT timings.

With resolved targets and no contention, first-ACT-through-terminal-recovery
totals are RowCopy(D)=40+5D+16 CK, MAJ3=66, MAJ5=76, NOT=99, and NOT_COPY=104
CK at `DDR4_2400R`. Physical-range or maintenance waiting and shared command
arbitration can increase request latency; distinguish them from local
primitive execution and recovery. Overlapped costs are not summed twice; the
totals already include terminal nRP.

**Movement timing**

One range-wide LC-MOV is one invocation whose selected mats progress in
lockstep; range length changes payload width, not occurrence count or
isolated latency. Singleton GB retains two separately issued endpoint
activations. No explicit Chip/Subarray/Mat timing hierarchy, per-link owner,
or same-cycle multi-command issue is added.

A movement occurrence may issue only when all four conditions hold:

```text
request eligible
prerequisite compatible
primitive-local timing ready
Device timing ready
```

The retained controller execution context owns relationships whose meaning
depends on primitive type, source/destination role, a particular earlier
occurrence of a repeated semantic command, or another occurrence-specific
condition, retaining the minimum occurrence issue history for them through
one localized mechanism rather than scattered LC/GB special cases. Device
timing remains authoritative for context-independent protocol, resource, and
recovery constraints expressible through hierarchy, command identity, and
command history. Primitive-local timing supplements rather than replaces
Device timing. Do not duplicate a constraint across both domains, add
timing-only command aliases, or encode timing readiness in Device state.

LC/GB Device relationships apply to the latest history of that movement
invocation, not the target Bank. Source PRE→destination ACT and terminal
recovery are footprint-local; a movement PRE never publishes a Bank/Rank
deadline against otherwise-disjoint PuD. Incoming conventional
PRE/PREab/autoprecharge/refresh recovery and shared Channel command issue
still apply. A locally timing-blocked occurrence does not reserve the
controller or Channel; unrelated eligible, timing-ready work in other Banks
remains selectable under existing arbitration and shared constraints, so
primitive-local readiness participates in scheduler candidate
readiness and final pre-issue validation.

Use the project `DDR4_2400R` baseline:

```text
tCK  = 833 ps
nRCD = 16 CK
nRTP = 9 CK
nRAS = 39 CK
nRP  = 16 CK
nWR  = 18 CK
```

These are project values inherited from the selected Ramulator2 preset, not a
claim that MIMDRAM evaluated the identical component-timing tuple or `2400R`
speed-bin suffix.

Adopt FIGARO's guarded value as an explicit simulator assumption:

```text
tRELOC = 1 ns
nRELOC = ceil(1000 ps / 833 ps) = 2 CK
```

FIGARO provides primary-source evidence for a related relocation mechanism
but does not directly validate MIMDRAM's exact LC local path or GB
neighboring-global-SA path; applying it to both is a project choice. Quantize
every independently enforced continuous interval independently,
`nX = ceil(tX / tCK)`. For LC, `nRELOC + nWR = 2 + 18 = 20 CK`; do not
re-quantize a rounded aggregate.

LC primitive-local dependencies:

| Predecessor | Following occurrence | Delay |
| --- | --- | ---: |
| occurrence 0 `ACT_MOV(source)` | occurrence 1 `RD_MOV(source)` | `nRCD = 16 CK` |
| occurrence 1 `RD_MOV(source)` | occurrence 2 source `PREpb` | `nRTP = 9 CK` |
| occurrence 4 `WR_MOV(destination)` | occurrence 5 terminal `PREpb` | `nRELOC + nWR = 20 CK` |

The first two edges adopt the source phase's regular `ACT-RD-PRE` readiness
structure without importing ordinary external-DQ timing into `RD_MOV`.
Retaining the HFF payload across source PRE adds no source-side relocation
delay.

LC Device relationships:

```text
latest invocation ACT_MOV -> PREpb  = nRAS = 39 CK
latest invocation ACT_MOV -> WR_MOV = nRAS = 39 CK
PREpb -> ACT_MOV                     = nRP  = 16 CK
```

The latest-`ACT_MOV` edges use history window 1. They constrain source PRE
from source ACT, and destination WR and terminal PRE from destination ACT.
Waiting for destination ACT plus `nRAS` before LC destination WR is an
explicit conservative simulator decision.

| Cycle | LC occurrence | Controlling readiness |
| ---: | --- | --- |
| 0 | `ACT_MOV(source)` | start |
| 16 | `RD_MOV(source)` | source ACT + `nRCD` |
| 39 | source `PREpb` | `max(source ACT+nRAS, RD+nRTP)` |
| 55 | `ACT_MOV(destination)` | source PRE + `nRP` |
| 94 | `WR_MOV(destination)` | destination ACT + `nRAS` |
| 114 | terminal `PREpb` | `max(destination ACT+nRAS, WR+nRELOC+nWR)` |
| 130 | recovery complete | terminal PRE + `nRP` |

```text
T_LC,sim = 2 * (nRAS + nRP) + nRELOC + nWR = 130 CK
```

MIMDRAM's source equation is `2*(tRAS+tRP)+tRELOC+tWR`. The post-`WR_MOV`
placement of `tRELOC` and serialization of `nRELOC+nWR` are project modeling
choices, not source-stated directed edges.

GB primitive-local dependencies:

| Predecessor | Following occurrence | Delay |
| --- | --- | ---: |
| occurrence 0 source `ACT_MOV` | occurrence 2 `RD_MOV(source)` | `nRAS = 39 CK` |
| occurrence 2 `RD_MOV(source)` | occurrence 3 `WR_MOV(destination)` | `nRELOC = 2 CK` |
| occurrence 3 `WR_MOV(destination)` | occurrence 4 terminal `PREpb` | `nWR = 18 CK` |

The source-RD dependency explicitly uses source ACT occurrence 0 even after
destination ACT occurrence 1 has issued. GB Device relationships:

```text
latest invocation ACT_MOV -> WR_MOV = nRAS = 39 CK
latest invocation ACT_MOV -> PREpb  = nRAS = 39 CK
PREpb -> later opening               = nRP  = 16 CK
```

For GB, the latest ACT is the destination occurrence. Preserve both visible
ACT occurrences and at most one issue per simulator tick without claiming
that MIMDRAM physically uses successive C/A cycles.

| Cycle | GB occurrence | Controlling readiness |
| ---: | --- | --- |
| 0 | `ACT_MOV(source)` | start |
| 1 | `ACT_MOV(destination)` | next simulator issue slot |
| 39 | `RD_MOV(source)` | source ACT occurrence 0 + `nRAS` |
| 41 | `WR_MOV(destination)` | `max(RD+nRELOC, destination ACT+nRAS)` |
| 59 | terminal `PREpb` | `max(WR+nWR, destination ACT+nRAS)` |
| 75 | recovery complete | terminal PRE + `nRP` |

Destination `ACT_MOV + nRAS = 1 + 39 = 40`, while source
`RD_MOV + nRELOC = 39 + 2 = 41`; the relocation dependency hides the one-CK
issue offset without subtracting a cycle or adding an alias.

```text
T_GB,sim = nRAS + nRELOC + nWR + nRP = 75 CK
```

MIMDRAM's source equation is `tRAS+tRELOC+tWR+tRP`. The
`RD_MOV(source) -> WR_MOV(destination) = nRELOC` edge is a simulator
decomposition of that aggregate equation. The exact physical GB C/A issue
relationship remains unknown. The 130/75 CK isolated baselines are not claims
about contended end-to-end latency.

Retain context-independent inherited recovery into the first `ACT_MOV`:

```text
PREpb -> ACT_MOV = nRP
PREab -> ACT_MOV = nRP
RDA   -> ACT_MOV = nRTP + nRP
WRA   -> ACT_MOV = nCWL + nBL + nWR + nRP
REFab -> ACT_MOV = nRFC
```

Terminal `PREpb` imposes ordinary `nRP` recovery before a later ordinary ACT,
PRADA opening command, another `ACT_MOV`, or `REFab` as applicable. Source
LC `PREpb -> destination ACT_MOV` is an instance of that general rule.

Keep three boundaries distinct:

```text
first ACT_MOV -> terminal PREpb issue
    visible sequence retirement and active-state close boundary

first ACT_MOV -> terminal PREpb recovery completion
    published-equation comparison boundary (both equations include tRP)

request depart/callback/statistics completion
    depart = terminal PREpb issue + nRP
```

Add no movement-specific `tRRD`, `tFAW`, activation-current rule, ordinary
same-Bank `nRC` constraint between the two GB activations, external RD/WR
burst/CAS/DQ-turnaround or sibling-rank DQ timing, or undocumented
Rank/Channel movement-datapath constraint. Each omission is a fidelity
limitation, not a physical exemption. The global-row-buffer and interconnect
are modeled to let disjoint GB endpoint footprints progress independently; no
shared link, current, DQ, or topology rule is inferred.

**Movement statistics**

Report LC-MOV and GB-MOV lifecycle statistics separately with no combined
movement statistic. At the controller level, register these fields only for a
movement-capable standard, using `lcmov` and `gbmov` as `<type>`:

```text
num_pud_<type>_reqs
num_pud_<type>_reqs_completed
pud_<type>_latency
avg_pud_<type>_latency
pud_<type>_moved_bits
```

At the memory-system level, expose `total_num_pud_lcmov_requests` and
`total_num_pud_gbmov_requests`. Increment a controller accepted count only
after successful pending-PuD-buffer enqueue, and its memory-system counterpart
only after controller `send()` succeeds; rejected or backpressured attempts
contribute nothing.

At depart, release footprint protection and extract/erase the delayed
completion; then increment the completed count, add `depart - arrive` to total
latency, and add exact moved bits, all before invoking the callback. An
accepted request that has not departed contributes to the accepted count only.
This is lifecycle accounting, not functional data validation; there is no
post-admission movement failure or abort.

```text
LC-MOV moved bits = (mat_end - mat_begin + 1) * hffs_per_mat
GB-MOV moved bits = hffs_per_mat
```

Derive moved bits from validated request metadata and typed `hffs_per_mat` at
completion; do not store a duplicated or rounded byte size. Movement
contributes nothing to ordinary Read/Write accepted/served,
forwarding/coalescing, row-buffer, or byte-throughput statistics. Derive each
average as total latency divided by completed count, or zero when none has
completed, during statistic update/finalization. Add no movement
rate/bandwidth, per-mat, per-occurrence, functional-data, or trace statistic.
Combined counts, bits, and averages remain externally derivable from the
separate LC/GB aggregate counters.

Rationale

A hybrid on one canonical substrate supports the intended combined PRADA and
movement experiments without making movement choices retroactive PRADA
properties. One request per architectural movement invocation matches the
LC-MOV/GB-MOV boundary described by MIMDRAM without prematurely defining
batching, address progression, routing, or software lowering; controller
ownership follows from the compound, ordered visible sequence.

Disjoint overlap preserves MIMDRAM's defining MIMD capability. Shared state
per lockstep range avoids duplicated per-mat phase/history while preserving
independent rows, progress, and recovery. Physical-mat exclusion follows the
accepted project inference from MIMDRAM selection and circuitry; the single
occupied-subarray boundary avoids importing SALP. Footprint protection through
recovery is a physical execution constraint independent of control-engine
accounting. Prior-work engines execute bbop/microProgram contexts, whereas a
primitive-level engine charge would count physical compute primitives and
exclude movement; the papers and inspected public artifacts do not supply a
complete finite-control model connecting those contexts to evaluated BLP/SALP.
Omitting that bottleneck explicitly is the selected performance abstraction;
neither primitive E=8 nor a speculative parent-context model is justified by
the reported count alone. Canonical location identity does not require timing simulation to
store functional values. Fixed local compute phase costs expose the hybrid
timing assumption without inventing width scaling. The four-residual/host
boundary follows the available reduction evidence and connectivity while
leaving arithmetic construction to the macro layer.

Resolved range metadata already supplies the selected-mat identity; consuming
it at activation preserves range-local execution while avoiding a physical
transport model whose queue, preparation, and bus-reservation semantics would
be specific to the project hybrid. Omitted costs are stated explicitly.

Visible occurrences preserve the source-described phase boundaries and both
GB endpoints, while shared semantic identities avoid encoding controller roles
as Device commands. Controller-owned progress is necessary because Device
handlers lack retained request/cursor context. Continuous footprint ownership
protects LC retained validity and both GB endpoints; retiring at terminal PRE
while protecting recovery separates sequence completion from resource reuse
without save/resume rules. The two movement states are the minimum under the
continuous Device-marking and shared-`PREpb` model: one marks occupancy and one
distinguishes the unconsumed source-data condition that source PRE must
preserve.

Splitting timing responsibility lets static Device history enforce general
resource/recovery rules while the retained context selects particular
occurrences, especially GB's source ACT after the destination ACT becomes the
latest Device history entry, and lets other Banks progress during local
timing gaps. The directed graphs retain every visible occurrence and
independently quantized interval while reproducing the two conservative
source-equation structures. The rounding calculation preserves the reported
ACT-overhead boundary without adding unsupported integral-cycle penalties.

Separate accepted and completed counts expose pending lifecycle work, while
completion-time exact-bit accounting describes only departed requests.
Per-primitive totals preserve the different LC range-width and GB singleton
semantics and keep ordinary byte-throughput meaning.

Evidence

- **Provenance.** Consolidated on 2026-11-19 from five now-Superseded
  decisions, which retain acceptance-time history, the Bank-serialized
  movement policy, the Alternative-A/Q=8 transport design, and legacy
  development labels:

  | Former label | Accepted | Superseded source |
  | --- | --- | --- |
  | Gate A (experiment/substrate boundary) | 2026-09-08 | [substrate and movement request boundary](superseded/mimdram-substrate-and-movement-request-boundary.md) |
  | Gate C execution/lifecycle | 2026-09-09 | [execution, ownership, and Device](superseded/mimdram-movement-execution-ownership-and-device.md) |
  | Gate C timing/resources | 2026-09-09 | [timing and resource model](superseded/mimdram-movement-timing-and-resource-model.md) |
  | T-A resolved-target transport | 2026-09-09 | [mat-target transport abstraction](superseded/mimdram-mat-target-transport-abstraction.md) |
  | Gate B (placement) | 2026-09-08 | moved to the [geometry decision](mimdram-geometry-and-placement.md) |

  The movement footprint refinement and the no-finite-control-engine common
  execution model were Accepted on 2026-09-16; the latter moved here from the
  [multistandard decision](pud-multistandard-substrate.md) on 2026-11-19
  (acceptance-time text in Git history at `3cd4204`). The finite-engine code
  was removed in the common correction recorded in the completed
  [multistandard plan](../plans/completed/pud-multistandard-substrate-plan.md). Alternative-A/Q=8 code is
  retained in Git history at `0ce6922` for possible sensitivity analysis.
- **Source facts.** The
  [MIMDRAM movement reference](../references/mimdram-inter-column-data-movement.md)
  is authoritative for LC/GB mechanisms and aggregate equations, HFF retention
  across source PRE, the GB dual-activation and global-SA path, physical PRE
  uncertainty, mat-selection queues and enqueue/dequeue (§1.2), evaluated
  engines/buffers, fine-grained ACT overhead, reduction to four residuals,
  deterministic PUD command ordering, already-active maintenance behavior,
  and FIGARO's raw and guarded relocation evidence. MIMDRAM supports physical
  mat selection and independent work on disjoint ranges but does not specify
  all six pairwise concurrency cases; its overlapping GB endpoint activations
  describe concurrency within one movement invocation, not between
  independent GB requests. [PRADA primitives](../references/pud-primitives.md)
  and [compute timing evidence](../references/ddr4-pud-timing-reference.md)
  supply compute mechanisms and derivations.
- **Project decisions.** Footprint ownership, semantic IDs,
  invocation-local states, resolved-target transport, the timing-domain split,
  the selected baseline, the application of `tRELOC`, directed-edge
  placements, F-A refresh behavior, and the listed omissions are simulator
  decisions, not source claims.
- **Implementation.** [RequestLocations](../../../src/ramulator/base/request.cpp)
  derives the normalized physical footprint;
  [GenericDDR](../../../src/ramulator/controller/impl/generic_ddr_controller.cpp)
  and [Device](../../../src/ramulator/dram/device.cpp) use protected
  invocation contexts and consume resolved occurrence associations;
  [controller completion](../../../src/ramulator/controller/controller_base.cpp)
  retains protection through recovery, extracts completions before callbacks,
  and registers the movement statistics;
  [occurrence sequencing](../../../src/ramulator/controller/pud_sequence.cpp)
  holds Request-local timing history. Movement edges are declared in
  [ddr4_pud_movement.py](../../../python/ramulator/dram/ddr4_pud_movement.py)
  and generated by [spec.py](../../../python/ramulator/dram/spec.py) as Bank
  edges that retain numeric authority, but associated Device dispatch checks
  them against Request-local invocation history; the same seam enforces the
  six occurrence-specific LC/GB edges, while incoming conventional recovery
  and shared Channel timing still use the hierarchy. Controllers reject the removed `pud_compute_engines`
  parameter. AQUA and RRS reject movement-capable standards at setup.
  Verification is recorded in the completed
  [v2 plan](../plans/completed/mimdram-pud-substrate-v2-implementation-plan.md)
  and [footprint plan](../plans/completed/pud-movement-footprint-plan.md).
  Decimal arithmetic verified the four upper-envelope ceiling results.

Open issues

- Physical validation of mat-selective PRE and independent disjoint GB
  global-row-buffer/interconnect progress; these remain simulator assumptions.
- Physical validation or refinement of the LC/GB `tRELOC` placement, LC
  relocation/write serialization, and GB directed decomposition; physical
  movement command encoding and exact C/A-bus occupancy.
- Whether stronger evidence requires movement `tRRD`, `tFAW`,
  activation-current, ordinary row-cycle, DQ, or additional shared
  Rank/Channel rules.
- Any transport sensitivity study must explicitly select and report its
  fidelity; physical validation of the historical PRADA transport mapping is
  unresolved.
- Portability of the numeric assumptions to another timing preset,
  organization, or DRAM standard.
- Exact pending admission and mixed-traffic arbitration details that do not
  change the accepted ownership policy.
- Future self-contained request reconstruction or movement-enriched trace
  formats, and movement-aware mapping that could make AQUA or RRS compatible.
- Future refresh deadline, retention, credit, and maximum-deferral fidelity
  beyond F-A.
- Out of scope: SALP-style cross-subarray execution, finite control-engine
  modeling, host/cache coherence, and mixed ordinary/PuD functional coherence.
- Later operation-layer work above the one-invocation request boundary:
  workload/frontend integration, `bbop_mov` lowering, array placement,
  batching, and routing.
