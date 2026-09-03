Status: Accepted

Question

What ownership, atomicity, sequence-integrity, acquisition, release, and
interleaving policy should apply while an LC-MOV or GB-MOV executes its
visible movement-command sequence?

Decision

Use continuous, non-preemptive Bank ownership across the protected movement
sequence for each LC-MOV and GB-MOV in the initial combined movement
substrate. The protected sequence begins when the first intended
movement-specific command role actually issues and ends when the terminal
movement-close role issues.

Later resolution: under
`docs/pud/decisions/mimdram-movement-occurrences-and-command-identities.md`,
the first protected occurrence is `ACT_MOV`, and terminal movement-close means
the movement request's terminal `PREpb` occurrence. Shared command identities
do not change the ownership lifetime accepted here.

A movement request waiting in the pending queue owns no resource. An ordinary
preparatory prerequisite issued before the first intended movement-specific
role does not acquire ownership. If unrelated same-Bank activity subsequently
invalidates that preparation, the pending movement request may resolve the
necessary prerequisite again.

Acquire Bank ownership atomically when the first intended movement-specific
role issues. Retain the movement request in the active buffer from that issue
through its terminal movement-close role. The retained active movement request
is the authoritative owner of its Bank. Do not introduce a separate
Bank-owner table or mat scoreboard.

While ownership is active, reject before prerequisite resolution every
independent candidate whose complete command scope intersects the owned Bank.
This includes ordinary traffic, independent LC-MOV and GB-MOV requests,
inherited RowCopy, MAJ3, MAJ5, and NOT requests, row-policy work, refresh and
other priority maintenance, and plugin-generated commands.

The active owner's current intended movement role remains eligible. A
prerequisite generated for that intended role may also issue as work belonging
to the owner and does not advance the movement sequence cursor. This decision
does not define which concrete prerequisites exist or whether ordinary
commands are valid movement prerequisites.

Use one monotonic movement sequence cursor. Select operand 0 or operand 1
according to the accepted source/destination role sequence, and advance the
cursor only when the intended movement-specific role itself issues.

Commands whose complete scope avoids the owned Bank remain eligible between
movement roles, subject to existing arbitration and accepted timing
constraints. Bank ownership does not globally serialize the controller.

Release ownership when the terminal movement-close role issues. Terminal
recovery, request departure, callback, and statistics completion are separate
timing and lifecycle events and may occur later.

Do not initially support preemption, abort, save/restore, pause/resume, or
restart after maintenance interruption.

Preserve the existing active-before-priority ordering and FIFO priority-head
behavior. Do not add scope-aware priority bypass or detailed refresh-deadline
policy in this decision.

Later resolution: the focused refresh investigation classified the initial
model as F-A. It intentionally inherits GenericDDR's deferred-refresh
behavior: queued priority refresh prevents pending movement acquisition,
refresh generated after acquisition waits for the non-preemptive movement,
and terminal `PREpb` releases ownership while Device timing retains `nRP`
protection before `REFab`. No deadline, maximum-deferral credit, or
deadline-aware admission is added. Their absence remains a GenericDDR
fidelity limitation and is not plan-shaping for the initial movement model.

Future MIMDRAM-MIMD support may refine Bank ownership into finer mat-range or
movement-resource ownership without changing the accepted LC-MOV/GB-MOV
request boundary, placement contract, or visible command-role semantics.

Rationale

Continuous Bank protection preserves LC-MOV's retained source payload and
GB-MOV's partially progressed endpoint activation and transfer conditions
without requiring independent same-Bank requests to understand, save, or
restore intermediate movement state. The Bank scope follows the accepted
initial Bank-conservative inter-request resource abstraction; it is a project
modeling choice rather than a MIMDRAM source fact.

Beginning ownership only when the first intended movement-specific role
issues matches the existing DDR4_PuD retained-request methodology and avoids
reserving a Bank while a movement is merely admitted, queued, or performing
ordinary preparation. It also avoids assigning movement-specific persistent
meaning to prerequisites before the later state and prerequisite decision
defines them. The controller issues at most one command per tick, so the
request can become the retained authoritative owner atomically with the first
role's issue.

Pre-prerequisite rejection prevents an independent request from inspecting or
altering the owned Bank's intermediate movement condition. Exempting the
retained owner lets its intended roles and any prerequisites generated for
them make progress without treating those prerequisites as independent
conflicts. Advancing the cursor only for the intended role preserves sequence
integrity when a prerequisite is issued instead.

Allowing commands whose complete scope avoids the owned Bank preserves
existing different-Bank progress during movement timing gaps. Per-phase
reservation would allow only unsupported temporal same-Bank interleaving under
the current Bank-conservative resource model while requiring explicit
intermediate-state preservation and save/resume rules. A narrower hybrid
critical section cannot be defined cleanly before movement state and timing
semantics are accepted; for the visible roles, the physically sensitive
interval begins no later than the first movement role and continues through
terminal close.

Releasing ownership at terminal close separates sequence integrity from
physical recovery. Later directed timing constraints can delay conflicting
reuse without retaining request ownership, and external completion can remain
at its separately accepted lifecycle boundary.

Preserving existing priority behavior avoids introducing a new generic
scheduling policy as part of movement atomicity. Avoiding interruption also
removes the initial need for abort, save/restore, or resume mechanisms, at the
cost of potentially longer Bank occupation and maintenance deferral.

Evidence

MIMDRAM source facts:

- `docs/pud/references/mimdram-inter-column-data-movement.md` records that the
  mat scheduler marks an available contiguous mat range busy before assigning
  a PUD operation to a free muProgram processing engine, and frees the mats
  when that engine finishes.
- The same reference records that multiple muProgram engines may execute
  allocated operations concurrently, that mats in one allocated range share
  state while executing the same ACT-PRE sequence, and that ACT/PRE ordering
  within a muProgram cannot be reordered.
- The reference records that AAP/AP PUD work waits when Bank maintenance is
  already in progress.
- The source does not establish movement-specific ownership lifetime,
  phase-level interleaving, interruption, pause/resume, refresh preemption, or
  a mapping from mat-range reservation to whole-Bank reservation.

Accepted project decisions:

- `docs/pud/decisions/mimdram-substrate-and-movement-request-boundary.md`
  defines one request as one architectural LC-MOV or GB-MOV invocation and
  places movement request lifecycle and sequencing in the controller.
- `docs/pud/decisions/mimdram-movement-range-and-placement.md` accepts
  range-wide lockstep LC-MOV, singleton directional-neighbor GB-MOV, and
  same-Bank/derived-subarray placement while leaving independent-request
  concurrency unresolved.
- `docs/pud/decisions/mimdram-movement-occurrences-and-command-identities.md`
  accepts six ordered LC-MOV occurrences and five ordered GB-MOV occurrences,
  with retained request operands and monotonic controller sequence progress.
- `docs/pud/decisions/mimdram-movement-timing-resource-scope.md` assigns
  independent same-Bank movement and inherited DDR4_PuD roles to one
  conservative conflicting resource domain while explicitly deferring
  continuous reservation, ownership lifetime, release, atomicity, and
  preemption to this decision.
- `docs/pud/decisions/pud-controller-sequencing-and-atomicity.md` and
  `docs/pud/decisions/pud-request-lifecycle-queueing-and-statistics.md` provide
  the existing DDR4_PuD methodology: a retained active request supplies Bank
  ownership and monotonic progress; ownership begins with the first intended
  PuD activation, prerequisites do not advance progress, different-Bank work
  may continue, and ownership release is separate from delayed completion.

Repository evidence:

- `src/ramulator/controller/impl/generic_ddr_controller.cpp` retains active
  DDR4_PuD requests, derives ownership eligibility from those requests before
  prerequisite resolution, advances `pud_sequence_index` only when the
  intended command issues, and gives active requests precedence without
  preventing timing-ready work in different Banks.
- `src/ramulator/controller/controller_base.cpp` preserves FIFO priority-head
  handling, tracks active requests per Bank for close protection, and
  separates active-request retirement from delayed request completion.
- `src/ramulator/controller/scheduler/impl/frfcfs.cpp` and
  `src/ramulator/controller/scheduler/impl/frfcfs_rowhit.cpp` already accept a
  pre-prerequisite eligibility predicate without changing the semantic
  placement of the existing command filter.

Open issues

- Exact movement device states, including LC retained-payload visibility and
  GB source/destination activation or global-SA/link visibility.
- Exact prerequisite and action tables for every movement role.
- Whether ordinary commands can serve as movement prerequisites.
- Movement-specific close/precharge scope, state transition, and legality.
- Whether a later accepted state model introduces an earlier operation that
  creates persistent movement state. If so, that operation must be treated as
  part of the protected movement sequence and the acquisition boundary must
  be reconsidered explicitly.
- Exact numeric directed timing edges and values, including the mapping of
  `tRAS`, `tRP`, `tWR`, and `tRELOC`.
- The GB-MOV activation-role issue gap, physical-overlap representation, and
  aggregate-latency treatment.
- CK quantization, command encoding, command-bus occupancy, `tRRD`, `tFAW`,
  and other shared Rank/Channel constraints.
- Terminal-close recovery duration and the commands constrained by that
  recovery.
- Movement Column units, valid range, alignment, and HFF-selected datapath
  mapping.
- Detailed refresh deadlines, maximum deferral, credits, retention
  guarantees, admission policy near a deadline, and priority-buffer overflow
  behavior.
- Whether scope-aware priority-head bypass is desirable as a later scheduling
  policy.
- Detailed row-policy behavior and physical validation of behavior-changing
  plugins for movement-specific roles.
- Exact request departure, callback, statistics-completion, and modeled data
  availability cycles.
- Movement-specific statistics and completion ordering among movement,
  inherited PuD, and ordinary Read requests.
- Future mat/range/link availability, multiple same-Bank contexts, and
  movement-specific pairwise concurrency rules for MIMDRAM-MIMD support.
