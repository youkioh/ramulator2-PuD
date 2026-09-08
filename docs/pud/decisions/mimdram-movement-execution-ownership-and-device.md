Status: Accepted

Question

What visible occurrences, semantic command identities, controller ownership,
Device states/actions, prerequisites, maintenance policy, and lifecycle
statistics/accounting should the initial LC-MOV and GB-MOV model use?

Decision

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
- Future same-Bank disjoint-mat MIMD, which requires a new finer-grained
  ownership, legality, resource, and Device-state decision.
- Future refresh deadline, retention, credit, and maximum-deferral fidelity
  beyond the accepted initial F-A policy.
