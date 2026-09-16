Status: Accepted

Question

What execution state, ownership, admission, close/recovery, and completion
contract realizes MIMDRAM-v2 Gate A/B? What visible occurrences, Device
states/actions, maintenance, and accounting govern the retained LC/GB model?

Decision

**Finite-engine amendment (Accepted 2026-09-16).** The
[common execution-model decision](pud-multistandard-substrate.md#accepted-common-execution-model--no-finite-control-engine-capacity-2026-09-16)
supersedes only this document's finite primitive-engine-accounting clauses.
Finite SIMDRAM/MIMDRAM control-unit capacity is outside the performance model:
compute primitives and LC-MOV/GB-MOV all have no finite control-engine charge.
Physical footprint ownership/conflicts, no-SALP, command/movement timing,
terminal recovery and conventional/PuD protection remain in force. The old
Phase-1 E=8 implementation persists until separately authorized code correction;
its results are historical implementation evidence, not the amended model.

**Current status (2026-09-10).** W1-W9 implemented this range-local execution,
protected recovery, conflict, maintenance, and completion authority inside the
canonical [unified DDR4 PuD substrate](ddr4-pud-unified-substrate.md).
`v2` and `legacy` below are development/provenance labels, not selectable
execution branches. The movement footprint refinement accepted on 2026-09-16
below replaces the former Bank-aggregate movement scope in this unified model.
Statements that public execution was not implemented, and acceptance-time
implementation/open-detail notes, are
historical; the explicitly listed physical-fidelity and out-of-scope limits
remain current.

**Accepted v2 Gate C: execution and lifecycle, 2026-09-09**

This is the canonical Gate C execution/state/lifecycle authority, paired with
the [timing and transport authority](mimdram-movement-timing-and-resource-model.md).
Apply these v2 refinements with Accepted [Gate A](mimdram-substrate-and-movement-request-boundary.md)
and unchanged [Gate B](mimdram-addressing-geometry-and-payload.md). The legacy
movement contract below remains the authority for the existing executable
baseline and for v2 movement provisions not refined here. Recording Gate C
does not implement v2 or authorize an implementation plan.

The following v2 rules are **Accepted project decisions**, not assertions of
physical equivalence to MIMDRAM. Source facts and implementation facts are
identified in Evidence and in the linked technical reference.

**Range contexts and temporal state**

Use one temporal execution context per allocated lockstep compute range or
acquired movement invocation.
Derive mat availability from protected active/recovering range records;
independent full state per mat and a replica of the physical scoreboard are
unnecessary. Retain each range's resolved Gate B identity, operand/activated-row
context, phase, occurrence progress, and local timing history. Controller
sequencing owns primitive identity, operand ordering, and the next occurrence;
Device legality must distinguish independent range phases. Concrete C++
ownership/factoring is not selected by this contract.

Keep conventional Bank row state separate. Every activation, N, and close
must retain its own resolved target/context; another range's command must not
overwrite that association. A Bank-global last-selected-range variable is
insufficient. Gate B selects locations; this decision selects temporal effects.

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

**Resources and admission**

**Superseded finite-engine rule / current implementation history:** the
original profile used configurable E (default eight), one compute primitive
Request per slot, shared across each controller/Channel's Ranks/Banks, with
E=1/2 overlap controls. This was a project implementation choice, not faithful
bbop/microProgram accounting. The common amendment removes that performance
constraint; it does not replace it with per-Bank or parent-operation pools.

Scan pending compute oldest-to-newest using online first fit: allocate the
first request whose complete range is available, subject to ordinary/movement,
subarray, and maintenance eligibility. No finite control-engine slot is required.
Allocation is distinct from command arbitration and local timing readiness.
Reserve the complete physical range atomically on allocation, including any
pre-first-ACT wait for normal arbitration or local timing. T-A adds no target-delivery wait.
An unallocated pending request owns nothing.
Retain request-count pending buffering; do not reproduce the 2 kB bbop-buffer
hardware or equate its byte capacity with engine count.

Within a Bank, permit independent disjoint compute ranges in one subarray.
Intersecting mat resources conflict even when operand rows differ. Do not
allocate compute in a different subarray of that Bank until all protected
contexts there, including recovery, drain. SALP is not implicit in distinct
Gate B CellIDs. Different Banks may progress subject to shared issue,
maintenance, and applicable timing constraints.

**Accepted movement footprint refinement (2026-09-16).** Every PuD invocation
exclusively protects its physical mat footprint: compute and LC use the selected
MatRange; GB uses the union of its existing resolved source and destination
singleton endpoints. Derive chip/local-mat segments through the retained
resolver, ignoring operand rows and columns for resource intersection. Do not
duplicate placement formulas or invent additional GB topology.

PuD conflict scope = physical mat-footprint intersection + separately modeled
shared command/timing constraints. All six compute/LC/GB pair classes permit
concurrent progress on disjoint footprints within the same legal subarray;
intersections serialize through recovery. Same-Bank different-subarray work
still waits for every protected context to drain; this introduces no SALP.

Movement acquires its complete footprint atomically with first ACT_MOV, owns
nothing before that issue (including preparatory ordinary PRE), and retains
protection through terminal PRE+nRP. Terminal PRE retires the sequence; recovery
completion releases protection and completes accounting/callback exactly once.
Like compute, it has no finite control-engine charge. Failed admission is
retryable without partial ownership. A per-invocation context replaces Bank
movement state; the existing Request remains the sole cursor/history and
endpoint authority.

Ordinary Device-issued ACT/RD/WR/RDA/WRA and unrelated Bank PRE
conflict with protected same-Bank PuD contexts. Existing ordinary activity must
drain and conventional close/recovery must complete before compute allocation.
A preparatory ordinary PRE does not advance a PuD occurrence cursor.

Eligibility applies before prerequisites and again before issue, including
complete maintenance/plugin scopes. Preserve active-continuation precedence,
FIFO priority-head blocking, and existing ordinary/movement command arbitration;
compute allocation uses the first-fit policy above. Timing-blocked contexts
do not monopolize shared command issue.

**Recovery, maintenance, and completion**

At terminal compute PRE issue T, remove the sequence from command scheduling
but retain its range recovery exclusion. At T+nRP:

```text
release range recovery exclusion
complete request/accounting and invoke callback exactly once
```

Use the shared delayed-completion mechanism. Extract/erase a ready completion
before callback; preserve departure reordering and reentrant submission safety.
Compute and movement both retain physical footprint protection through
recovery, independently of any engine ID. Recovery does not reset another
context. The former compute-engine retention/release rule is superseded;
current code still releases its old engine record at this same recovery boundary.

Queued priority maintenance stops new allocations through the retained priority
policy; already allocated contexts drain without interruption. PREab/refresh
waits for every intersecting context and its recovery, with whole-scope
validation before mutation. Issue conventional PREab only when required by
remaining ordinary row state, then honor its recovery. Already-active
maintenance prevents affected starts until its applicable timing expires.
No refresh deadline admission, deferral-credit, retention guarantee, pause/resume,
or scope-aware priority bypass is added.

Dependent macro operations must wait for all required producer completions,
including destructive-operand/temporary-row reuse. Submission order and conflict
exclusion alone do not establish dependencies. No dependency-graph scheduler
or earliest electrical data-visibility claim is introduced.

**Movement metadata and the functional split**

Keep LC/GB occurrences and temporal validity, adding only resolved endpoint/row
identity needed for coherent targeted actions. LC source PRE closes the selected
source activation while preserving source-payload-valid metadata through source
recovery and destination ACT. WR_MOV consumes that validity; terminal PRE
closes the destination. GB retains its two endpoint activation conditions and
source-valid condition until WR_MOV; terminal PRE closes both endpoints.
These close scopes are simulator refinements, not recovered physical PRE wiring.
Movement footprint exclusion persists through terminal recovery. Source PRE,
terminal PRE and recovery cannot reset or block a disjoint PuD context except
through a separately modeled shared constraint.

Ramulator stores no DRAM, SA, compute-working, or HFF payload values and has no
staged functional commit. The same request and canonical Gate B resolver feed
the timing/state model and a separate PuD functional simulator. Actual values
for all five compute primitives and LC/GB belong to that functional simulator;
the timing callback establishes completion ordering, not a bit-storage API.
Do not modify ordinary forwarding/coalescing or add ordinary RD/WR value
simulation. Host/cache coherence and mixed ordinary/PuD functional coherence
remain outside this substrate contract.

**Retained movement sequence and lifecycle contract**

The following preserves command identities, ordering, validity and completion
semantics under the footprint-local resource scope above.

Keep LC-MOV and GB-MOV as controller-sequenced request-level operations.
Preserve these Ramulator-visible command occurrences and potential timing
boundaries:

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

Use exactly three new semantic movement command identities: `ACT_MOV`,
`RD_MOV`, and `WR_MOV`. Reuse existing `PREpb`. The new names are simulator
identities, not names claimed by MIMDRAM. Source/destination, LC/GB, and
position are occurrence roles, not distinct command types. Do not add
source/destination or LC/GB variants, a movement-specific PRE, generic
`CLOSE`, or timing-only aliases. Existing `ACT_PUD`, `ACT_PUD_OC`,
`ACT_PUD_S`, and `ACT_PUD_S_OC` remain PRADA-specific and are not reused.
Ordinary `ACT`, `RD`, and `WR` are not reused because their conventional
flat-Bank, row-hit, host-DQ, row-policy, and statistics meanings do not apply
to the internal movement occurrences.

Set `is_opening=false`, `is_accessing=false`, and `is_closing=false` for all
three movement commands. Each has `BankTarget::Single`. These metadata fields
classify the current controller, row-policy, and plugin behaviors; they do not
describe every physical action represented by a command. Movement activation
therefore does not enter the generic active-buffer path or activation-based
RowHammer handling, and movement transfer phases are not ordinary row-buffer
accesses. Do not provide movement `rowhit` or `rowopen` handlers. Keep shared
`PREpb` metadata and its single-Bank target unchanged.

The retained request/controller execution context owns primitive identity,
the two ordered operands, logical-mat metadata, one monotonic occurrence
cursor, each occurrence's source/destination role, and the occurrence issue
history required by primitive-local timing. The cursor advances only when the
intended architectural occurrence issues. A preparatory prerequisite neither
advances the cursor nor substitutes, skips, or reorders an occurrence.

Use continuous, non-preemptive footprint ownership through recovery. Derive
availability from protected invocation records; no separate mat scoreboard or
link-owner table is required. Before prerequisite resolution and again before
issue, reject intersecting PuD work. Ordinary traffic and maintenance retain
their complete Bank/Rank scopes. Preserve active-continuation precedence,
FIFO priority-head blocking and promotion-backpressure handling.

Keep conventional Bank row state separate. Before first ACT_MOV it must be
drained and Closed, including conventional recovery. An ordinary preparatory
PRE does not acquire a footprint or advance the movement cursor. Another
request may reopen the conventional Bank before acquisition, requiring another
preparatory PRE.

The invocation's Device phase is MovementActive or MovementDataValid during
the sequence, and Recovering after terminal PRE. These are simulator validity
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
invocation's state. Movement never populates or changes conventional row state.
Exact physical mat-selective PRE wiring remains outside the modeled claim.

The Open and ClosedCAP row policies require no movement-specific production
behavior. ClosedCAP's exact `RD`/`WR` upgrade checks cannot convert movement to
`RDA`/`WRA`, and movement's non-accessing metadata cannot increment its CAP or
independently trigger policy-generated PRE. Shared movement `PREpb`
notifications may retain the existing close-bookkeeping path: movement enters
ownership from an already-Closed Bank or after a preparatory conventional
`PREpb`, and no movement occurrence increments the CAP, so the reset is
behaviorally inert. Ownership remains the protection against independently
queued policy work.

Pure observational controller plugins may observe issued movement commands;
this means command visibility only and does not imply functional movement-data
knowledge. For the initial milestone, keep the existing `CmdTraceRecorder`,
`BinTraceRecorder`, and `LiveTraceStreamer` schemas and lifecycle interfaces
unchanged. Their existing command identity, issue cycle, request type, source
ID, and occurrence address make movement commands visible. The occurrence
Column coordinate is the opaque movement selector already carried by that
address; tracing assigns it no additional physical meaning. RAM2BIN and live
events also retain their existing arrival field.

The fixed LC/GB sequence may be used to infer source/destination role and
occurrence position when the corresponding request stream is otherwise
identifiable, such as in an isolated directed trace. This is not a guarantee
for an arbitrary concurrent trace: the existing schemas have no unique request
identity and are not self-contained request-reconstruction formats. Do not add
logical-mat metadata, moved bits, explicit occurrence role/index, occurrence
history, or delayed departure/callback events to production traces in this
milestone. Movement statistics and exact-bit accounting are defined separately
below.

Plugins already incompatible because the combined standard lacks required VRR
or RFM capabilities remain rejected by their setup checks. Reject AQUA and RRS
at setup whenever the DRAM standard is movement-capable: their RIT
placement/remapping semantics are not functionally integrated with movement
operands. Future support requires an explicit movement-aware mapping decision
rather than relying on ownership or the current absence of functional data
modeling.

Ordinary ACT/RD/WR/RDA/WRA, unrelated PRE, PREab, and refresh cannot
interrupt any protected context within their complete scope. Device rejection
is defensive protection before timing or state mutation. Independent PuD
occurrences instead use their associated invocation and footprint checks.

Use the initial F-A refresh policy inherited from GenericDDR. A queued
priority refresh prevents a pending movement from acquiring ownership. A
refresh generated after acquisition waits for the non-preemptive movement.
After terminal PREpb retires the sequence, protected recovery retains exclusion
until nRP completes before REFab. Add no refresh
deadline, maximum-deferral credit, deadline-aware admission, pause/resume, or
priority bypass. The absence of a deadline model is an inherited GenericDDR
fidelity limitation, not a physical refresh guarantee.

Sequence retirement and active-state close at terminal PREpb are distinct
from footprint release at recovery completion. Request retirement, departure,
and callback timing are defined by
`mimdram-movement-timing-and-resource-model.md`.

Report LC-MOV and GB-MOV lifecycle statistics separately and add no combined
movement statistic. At the controller level, register these fields only for a
movement-capable standard, using `lcmov` and `gbmov` as `<type>`:

```text
num_pud_<type>_reqs
num_pud_<type>_reqs_completed
pud_<type>_latency
avg_pud_<type>_latency
pud_<type>_moved_bits
```

At the memory-system level, expose the accepted-request totals
`total_num_pud_lcmov_requests` and `total_num_pud_gbmov_requests`. Increment a
controller accepted count only after successful pending-PuD-buffer enqueue,
and increment its memory-system counterpart only after the controller
`send()` succeeds. A rejected or backpressured attempt contributes nothing.

Lifecycle completion accounting occurs at the accepted Gate A departure
boundary. If terminal PREpb issues at cycle T, schedulable state ends at T,
while depart = T+nRP. At depart, release footprint protection and extract/erase
the delayed completion before callback; then increment the completed-request
count, add `depart - arrive` to total latency, and add exact moved bits, all
before invoking the callback. An accepted request that has not reached
`depart` contributes to accepted count only: it contributes zero completed
requests, latency, and moved bits. This is lifecycle completion accounting,
not functional data validation; the model has no post-admission movement
failure or abort semantics.

Derive moved bits from the retained, validated request metadata and typed
`hffs_per_mat` configuration at lifecycle completion:

```text
LC-MOV moved bits = (mat_end - mat_begin + 1) * hffs_per_mat
GB-MOV moved bits = hffs_per_mat
```

Do not store a duplicated or rounded request byte size. Movement retains the
`size_bytes = -1` N/A contract and contributes nothing to ordinary Read/Write
accepted/served, forwarding/coalescing, row-buffer, or byte-throughput
statistics. Derive each average latency during statistic update/finalization
as total latency divided by completed-request count, or zero when none has
completed. Add no movement rate/bandwidth, per-mat, per-occurrence, functional-
data, or trace statistic. Combined counts, bits, and averages remain externally
derivable from the separate LC/GB aggregate counters.

Implementation impact is limited by this contract: GenericDDR sequence logic
must become extensible for LC/GB metadata and occurrence history; shared
`PREpb` plus `PREab`/`REFab` paths require explicit movement legality; and
capability detection must verify LC/GB support. These are implementation
consequences, not new movement semantics.

Rationale

For v2, shared state per lockstep range avoids duplicated per-mat phase/history
while preserving independent rows, progress, and recovery. Physical-mat
movement exclusion follows the accepted project inference from
MIMDRAM selection and circuitry; the single occupied-subarray boundary avoids
importing SALP. Footprint protection through recovery is a physical execution
constraint independent of finite control-engine accounting, which the common
amendment excludes. Canonical location identity does not require timing
simulation to store functional values.

The rationale below applies to the retained movement protocol.

Visible occurrences preserve the source-described phase boundaries and both
GB endpoints while shared semantic identities avoid encoding controller roles
as Device commands. Controller-owned progress is necessary because Device
handlers lack retained request/cursor context.

Continuous footprint ownership protects LC retained validity and both GB
endpoints. Retiring at terminal PRE while protecting recovery separates
sequence completion from resource reuse without save/resume rules.

Separate accepted and completed counts expose pending lifecycle work, while
completion-time exact-bit accounting describes only requests that have reached
the existing depart/callback boundary. Per-primitive totals preserve the
different LC range-width and GB singleton semantics. Reusing existing PuD
accepted/completed/total-latency/derived-average conventions keeps the new
state minimal and preserves ordinary byte-throughput meaning.

The two aggregate states are the minimum under the accepted continuous
Device-marking and shared-`PREpb` model: one marks movement occupancy and one
distinguishes the unconsumed source-data condition that source PRE must
preserve. More phase states would duplicate the controller cursor; one state
could not select both required PRE actions through the existing Device API.

Evidence

For Gate C, [the curated MIMDRAM reference](../references/mimdram-inter-column-data-movement.md)
records source facts: shared range state, oldest-to-newest first fit, eight
evaluated engines, a 2 kB bbop buffer, per-chip mat queues, and LC/GB temporal
conditions. The user accepted the v2 simulator choices on 2026-09-09, including
E=8, the timing/functional split, same-subarray MIMD, and recovery-time release.
Only the finite primitive-engine choice is now superseded; the reported
prior-work eight engines operate at bbop/microProgram granularity.

Current implementation: [RequestLocations](../../../src/ramulator/base/request.cpp)
derives one normalized physical footprint union; [GenericDDR](../../../src/ramulator/controller/impl/generic_ddr_controller.cpp)
and [Device](../../../src/ramulator/dram/device.cpp) use protected invocation
contexts. [Controller completion](../../../src/ramulator/controller/controller_base.cpp)
retains protection through recovery and extracts completions before callbacks.
The [milestone plan](../plans/pud-movement-footprint-plan.md) records verification.

MIMDRAM supports physical mat selection, independent work on disjoint ranges,
mat-local LC row-buffer/HFF/column resources, and explicit GB endpoints using
the neighboring global movement path. It does not explicitly specify all six
pairwise concurrency cases. Allowing disjoint compute/movement state to
progress independently, including the global-row-buffer/interconnect path for
disjoint GB endpoint footprints, is the accepted project inference, not
physically proven MIMDRAM behavior. Shared command/timing resources can still
limit observed overlap.

`docs/pud/references/mimdram-inter-column-data-movement.md` is the source-fact
authority for the detailed LC source/destination sequence, HFF retention
across source PRE, the GB dual-activation and HFF/global-SA path, physical PRE
uncertainty, deterministic PUD command ordering, and already-active
maintenance behavior. Footprint ownership, semantic IDs, invocation-local
states, and F-A refresh behavior are project simulator decisions, not source
claims.

Repository evidence is the retained-request/cursor controller architecture,
pre-prerequisite eligibility, one-command/one-address Device handlers, one
Bank state plus Row map, issue-time action/timing updates, existing PRE
dispatch, GenericDDR priority/refresh behavior, exact-ID ClosedCAP upgrades,
metadata-driven activation plugins, exact-ID RowHammer plugins, observational
issue hooks, the existing command/address trace records, and AQUA/RRS RIT
mutation plus injected traffic. These mechanisms support the accepted boundary
without explicit Mat hierarchy, a second owner map, or a movement-specific
trace schema.

The existing GenericDDR lifecycle increments accepted PuD counts only after
enqueue, retires terminal-PRE requests into a shared delayed-completion path,
extracts ready completions before callback, accumulates `depart - arrive`, and
derives average latency from completed count. GenericDRAMSystem records
accepted operation totals after controller success. The existing exact-bit
helper derives LC range width and singleton GB width from validated metadata
and typed `hffs_per_mat`; ordinary throughput uses only served Read/Write
counts and the DRAM transaction byte width.

This document consolidates the current accepted authority formerly carried by
`mimdram-movement-occurrences-and-command-identities.md`,
`mimdram-movement-ownership-and-atomicity.md`, and
`mimdram-movement-minimum-device-state-and-actions.md`. Those files remain as
historical provenance.

Open issues

- Physical validation of mat-selective PRE and independent disjoint GB
  global-row-buffer/interconnect progress; these remain simulator assumptions.
- Exact pending admission and mixed-traffic arbitration details that do not
  change the accepted ownership policy.
- Future self-contained request reconstruction or movement-enriched trace
  formats, if a later milestone establishes that their observability value
  justifies schema/version and decoder churn.
- Future movement-aware mapping semantics that could make AQUA or RRS
  compatible with movement operands.
- Implementation and v2 verification progress are recorded in the
  [implementation plan](../plans/mimdram-pud-substrate-v2-implementation-plan.md).
- SALP-style cross-subarray execution, finite control-engine modeling,
  host/cache coherence, and mixed ordinary/PuD functional coherence are outside
  the accepted profile.
- Future refresh deadline, retention, credit, and maximum-deferral fidelity
  beyond the accepted initial F-A policy.
