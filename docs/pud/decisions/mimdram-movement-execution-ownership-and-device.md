Status: Accepted

Question

What execution state, ownership, admission, close/recovery, and completion
contract realizes MIMDRAM-v2 Gate A/B? What visible occurrences, Device
states/actions, maintenance, and accounting govern the retained LC/GB model?

Decision

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

Use one temporal execution context per allocated lockstep compute range.
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

Use configurable E compute engines per modeled MIMDRAM control-unit instance,
initially E=8. E=2 is a small overlap-validation configuration; E=1 is a
serialized control and cannot establish the MIMD claim. For the initial
GenericDRAM profile, associate one control-unit instance with one
controller/channel instance, sharing its pool across that instance's Banks
and Ranks. This profile association is a simulator choice grounded in the
current one-controller-per-channel mapping, not a requirement on C++ storage.

Scan pending compute oldest-to-newest using online first fit: allocate the
first request whose complete range is available and for which an engine is
free, subject to ordinary/movement, subarray, and maintenance eligibility.
Allocation is distinct from command arbitration and local timing readiness.
Reserve engine and range atomically on allocation, including the pre-first-ACT
wait for target transport. An unallocated pending request owns nothing.
Retain request-count pending buffering; do not reproduce the 2 kB bbop-buffer
hardware or equate its byte capacity with engine count.

Within a Bank, permit independent disjoint compute ranges in one subarray.
Intersecting mat resources conflict even when operand rows differ. Do not
allocate compute in a different subarray of that Bank until all protected
contexts there, including recovery, drain. SALP is not implicit in distinct
Gate B CellIDs. Different Banks may progress subject to the engine pool,
shared issue, maintenance, and applicable timing constraints.

Compute/movement and every independent movement/movement pair remain
Bank-serialized. Movement keeps first-ACT_MOV acquisition and terminal-PRE
sequence retirement, followed by Bank-wide recovery exclusion. It retains
its existing per-Bank execution context rather than consuming the compute-only
engine pool. Ordinary Device-issued ACT/RD/WR/RDA/WRA and unrelated Bank PRE
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
but retain its engine allocation and range recovery exclusion. At T+nRP:

```text
release compute engine
release range recovery exclusion
complete request/accounting and invoke callback exactly once
```

Use the shared delayed-completion mechanism. Extract/erase a ready completion
before callback; preserve departure reordering and reentrant submission safety.
Early engine reuse at terminal PRE is not part of the initial profile. Recovery
does not reset another context, but occupied engines remain a finite resource.

Queued priority maintenance stops new allocations through the retained priority
policy; already allocated contexts drain without interruption. PREab/refresh
waits for every intersecting context and its recovery, with whole-scope
validation before mutation. Issue conventional PREab only when required by
remaining ordinary row state, then honor its recovery. Already-active
maintenance prevents affected starts until its applicable timing expires.
No refresh deadline admission, deferral-credit, retention guarantee, pause/resume,
or scope-aware priority bypass is added.

Dependent macro operations must wait for all required producer completions,
including destructive-operand/scratch reuse. Submission order and conflict
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
Movement Bank exclusion persists through terminal recovery.

Ramulator stores no DRAM, SA, compute-working, or HFF payload values and has no
staged functional commit. The same request and canonical Gate B resolver feed
the timing/state model and a separate PuD functional simulator. Actual values
for all five compute primitives and LC/GB belong to that functional simulator;
the timing callback establishes completion ordering, not a bit-storage API.
Do not modify ordinary forwarding/coalescing or add ordinary RD/WR value
simulation. Host/cache coherence and mixed ordinary/PuD functional coherence
remain outside this substrate contract.

**Retained legacy movement contract**

The following provisions describe the existing Bank-aggregate baseline;
where v2 needs a different context/scope, the Gate C rules above take precedence.

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

Use continuous, non-preemptive Bank ownership for the full protected
movement sequence. A pending request owns nothing. An ordinary preparatory
`PREpb` issued before the first `ACT_MOV` owns nothing. Acquire ownership
atomically when the first `ACT_MOV` issues, retain the request as the
authoritative Bank owner, and release ownership when the request's terminal
`PREpb` issues. Do not add a separate owner table or mat scoreboard.
If unrelated work reopens the Bank before acquisition, the pending request
may resolve its preparatory prerequisite again.

While ownership is active, reject before prerequisite resolution every
independent candidate whose complete scope intersects the owned Bank. This
includes ordinary traffic, independent LC-MOV/GB-MOV, inherited RowCopy,
MAJ3, MAJ5, and NOT work, row-policy work, `PREab`, refresh-generated close
or refresh, other priority maintenance, and plugin-generated behavior. The
owner's intended occurrence and any legitimate prerequisite for it remain
eligible. Different Banks may progress under existing arbitration and timing
constraints. Do not add pause, abort, resume, save/restore, restart after
refresh, or scope-aware priority bypass.
Preserve existing active-before-priority ordering and FIFO priority-head
behavior.

Use the Bank node as the only Device-visible movement state location and add
exactly two movement states:

```text
MovementActive
MovementDataValid
```

`MovementActive` is an aggregate simulator legality/occupancy marker for a
protected movement with no unconsumed source-data/path-valid condition in
Device state. It is not one physical MIMDRAM circuit state and may represent
physically different occurrence boundaries.

`MovementDataValid` represents the exposed, unconsumed source-data/path-valid
condition established by `RD_MOV`. For LC it persists before and after the
source `PREpb` and through destination `ACT_MOV` until `WR_MOV`. For GB it
represents the source HFF/global-SA path condition between `RD_MOV` and
`WR_MOV`.

Neither state stores request or ownership identity, LC/GB identity,
source/destination role, activation count, exact occurrence, operands, rows,
logical mats, timing progress, or data values. Do not add committed,
dual-active, destination-active, per-mat, HFF, global-SA, link, scoreboard, or
sidecar state. Movement activation does not use conventional `Opened` or
populate `m_row_state`.

Before the first `ACT_MOV`, a conventionally `Closed` Bank is directly legal.
A conventionally `Opened` Bank receives ordinary `PREpb` as a preparatory
prerequisite. An inherited PuD intermediate state is illegal. During
ownership, an intended occurrence must be compatible with the current
aggregate movement state. An incompatibility is illegal; prerequisites do
not synthesize an ordinary repair sequence.

Use these state-dependent actions:

| Command | Compatible state | Result |
| --- | --- | --- |
| first `ACT_MOV` | `Closed` | `MovementActive`; do not populate `m_row_state` |
| later `ACT_MOV` | `MovementActive` | remain `MovementActive` |
| later `ACT_MOV` | `MovementDataValid` | remain `MovementDataValid` |
| `RD_MOV` | `MovementActive` | `MovementDataValid` |
| `WR_MOV` | `MovementDataValid` | `MovementActive` |
| `PREpb` | `MovementDataValid` | remain `MovementDataValid` |
| `PREpb` | `MovementActive` | `Closed`; clear `m_row_state` defensively |

The accepted LC trace is:

```text
Closed
-> ACT_MOV -> MovementActive
-> RD_MOV  -> MovementDataValid
-> PREpb   -> MovementDataValid
-> ACT_MOV -> MovementDataValid
-> WR_MOV  -> MovementActive
-> PREpb   -> Closed
```

The accepted GB trace is:

```text
Closed
-> ACT_MOV -> MovementActive
-> ACT_MOV -> MovementActive
-> RD_MOV  -> MovementDataValid
-> WR_MOV  -> MovementActive
-> PREpb   -> Closed
```

Every transition occurs at command issue, not at physical completion. The
two GB activations remain separately issued and timing-visible even though
their represented physical activation intervals overlap.

`PREpb` is deliberately shared. Device state selects its aggregate action:

```text
MovementDataValid + PREpb -> MovementDataValid
MovementActive    + PREpb -> Closed
```

The controller cursor decides whether that PRE occurrence is architecturally
correct and ownership eligibility distinguishes owner-issued movement PRE
from unrelated PRE. The Device API does not reproduce request provenance or
the exact cursor. Reusing Bank-level `PREpb` does not claim physical whole-
Bank movement precharge; exact physical scope remains unresolved.

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

Ordinary `ACT`, `RD`, `WR`, `RDA`, `WRA`, inherited PuD work, `PREab`,
refresh, and refresh-generated close are illegal if their complete scope
intersects a Bank in either movement state. Ownership is the primary
controller protection and Device rejection is a defensive invariant. They
cannot interrupt, repair, or reset movement. Shared `PREpb` follows the
controller/Device boundary above.

Use the initial F-A refresh policy inherited from GenericDDR. A queued
priority refresh prevents a pending movement from acquiring ownership. A
refresh generated after acquisition waits for the non-preemptive movement.
After terminal `PREpb` releases ownership and closes Device state, inherited
Device timing preserves safe `nRP` recovery before `REFab`. Add no refresh
deadline, maximum-deferral credit, deadline-aware admission, pause/resume, or
priority bypass. The absence of a deadline model is an inherited GenericDDR
fidelity limitation, not a physical refresh guarantee.

Ownership/state cleanup at terminal `PREpb` issue is distinct from recovery
completion. Request retirement, departure, and callback timing are defined by
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
boundary. If terminal `PREpb` issues at cycle `T`, ownership and schedulable
state end at `T`, while `depart = T + nRP`. At `depart`, extract and erase the
delayed completion before callback; then increment the completed-request
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
while preserving independent rows, progress, and recovery. Bank-wide movement
reservation avoids unsupported I/O concurrency; the single occupied-subarray
boundary avoids importing SALP. Holding the engine through recovery is the
accepted conservative policy. Early engine release would require a later
justified optimization. Canonical location identity does not require timing
simulation to store functional values.

The rationale below remains applicable to the legacy movement boundary.

Visible occurrences preserve the source-described phase boundaries and both
GB endpoints while shared semantic identities avoid encoding controller roles
as Device commands. Controller-owned progress is necessary because Device
handlers lack retained request/cursor context.

Continuous Bank ownership protects LC's retained payload and GB's partially
progressed endpoint/path conditions without inventing unsupported same-Bank
mat concurrency or save/resume rules. Releasing at terminal PRE separates
sequence integrity from physical recovery.

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

Current implementation facts: [GenericDRAM](../../../src/ramulator/memory_system/impl/generic_dram_system.cpp)
maps each controller to one channel; [GenericDDR](../../../src/ramulator/controller/impl/generic_ddr_controller.cpp)
currently uses Bank ownership, and [Device/node](../../../src/ramulator/dram/node.h)
state/history cannot represent independent ranges. [The completion path](../../../src/ramulator/controller/controller_base.cpp)
and [lifecycle tests](../../../tests/controller_scheduling/GenericDDRController/test_movement_lifecycle.py)
already separate terminal issue and recovery callback. These are foundations,
not implemented or tested v2 behavior. No runtime suite was run for this
documentation acceptance.

`docs/pud/references/mimdram-inter-column-data-movement.md` is the source-fact
authority for the detailed LC source/destination sequence, HFF retention
across source PRE, the GB dual-activation and HFF/global-SA path, physical PRE
uncertainty, deterministic PUD command ordering, and already-active
maintenance behavior. The Bank ownership, semantic IDs, two aggregate
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

- Exact physical movement PRE scope below the accepted Bank-aggregate
  simulator abstraction.
- Exact pending admission and mixed-traffic arbitration details that do not
  change the accepted ownership policy.
- Future self-contained request reconstruction or movement-enriched trace
  formats, if a later milestone establishes that their observability value
  justifies schema/version and decoder churn.
- Future movement-aware mapping semantics that could make AQUA or RRS
  compatible with movement operands.
- Implementation and v2 verification progress are recorded in the
  [implementation plan](../plans/mimdram-pud-substrate-v2-implementation-plan.md).
- SALP-style cross-subarray execution, early engine reuse, host/cache coherence,
  and mixed ordinary/PuD functional coherence are outside the accepted profile.
- Future refresh deadline, retention, credit, and maximum-deferral fidelity
  beyond the accepted initial F-A policy.
