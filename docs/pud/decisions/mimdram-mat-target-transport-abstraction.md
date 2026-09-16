Status: Accepted

Question

How should the baseline MIMDRAM/PRADA simulator represent delivery of the
resolved mat range to each PuD activation?

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

Accept the user-selected resolved-target abstraction on 2026-09-09. This is
the current baseline mat-target transport authority. It supersedes only the
Alternative-A/Q=8 transport requirements in the canonical
[Gate C timing/resource decision](mimdram-movement-timing-and-resource-model.md).
Earlier Gate A overhead-accounting and Gate C pre-first-ACT transport-wait
wording is subject to this abstraction; other timing, resource, allocation,
ownership and recovery requirements remain in force.

**Project simulator abstraction.** Every PuD request/occurrence retains its
resolved target metadata. The Device may consume the corresponding row and
resolved `MatRange` atomically when `ACT_PUD*` issues:

```text
Request / PuDOccurrence
    row + resolved MatRange
         |
         v
    ACT_PUD* Device action
```

The baseline models the selected-mat effect and abstracts physical delivery
of the selection. This is a simulation abstraction, not a new DRAM command,
hardware design, or claim that DDR4 can encode the range on the same C/A pins
in the ordinary ACT cycle. Each compute occurrence, including N and PRE,
keeps its explicit range/context association; this does not introduce a
Bank-global or implicitly persistent selection.

The baseline excludes per-chip mat-information FIFO occupancy, Q=8 as a
performance/resource constraint, ACT-enqueue/PRE-enqueue/ACT-dequeue execution,
per-activation target-descriptor preparation, T+1 target-transport events,
T+2 target-readiness state, initial one-CK target-only setup events, and
mat-target-specific C/A contention. Ordinary command issue arbitration and
applicable shared timing remain modeled.

Keep W1 canonical geometry and resolved `MatRange`, profile-defined mat/chip
topology, explicit range association on every compute occurrence, range-local
compute state, PRADA local primitive timing, and W4/W5 recovery, ownership and
conflict rules. W7 physical-range allocation and MIMD scheduling remain;
its former independent E=8 engine default is superseded by the common amendment.
LC/GB local timing and their existing transport-fidelity boundary are unchanged.

**Alternative-A status.** Alternative A was the project's mapping of
MIMDRAM's physical target-transport mechanism onto PRADA's sequential
activation commands. Neither the term nor that PRADA mapping was specified
by MIMDRAM. The detailed Alternative-A/Q=8 implementation is retained in Git
history at `0ce6922` for possible sensitivity analysis or optional future
fidelity; it is no longer the baseline substrate contract. This abstraction
also does not select the earlier persistent-selection hardware Alternative B.

**Explicit fidelity limitation.** Baseline performance results do not include
mat-information transport latency, mat-queue occupancy stalls, or C/A
contention caused specifically by mat-information delivery. These effects are
omitted, not physically zero. Report this limitation with baseline results;
do not claim physically complete MIMDRAM target-transport performance.

The separately authorized W6 baseline alignment implements this contract.
Implementation progress, validation and regression limitations are recorded in
the [implementation plan](../plans/mimdram-pud-substrate-v2-implementation-plan.md).

Rationale

Resolved range metadata already supplies the simulator's selected-mat
identity. Consuming it at activation preserves the intended range-local
execution while avoiding a physical transport resource model in the baseline.
The detailed alternative exposes additional transport costs but introduces
queue, preparation and bus-reservation semantics specific to the project
hybrid. Deferring that fidelity keeps the baseline focused on the accepted
compute, recovery and MIMD mechanisms, with omitted costs stated explicitly.

Evidence

- **MIMDRAM source fact:** the unchanged
  [technical reference, §1.2](../references/mimdram-inter-column-data-movement.md#12-fine-grained-mat-access-structures)
  records physical mat-selection communication using per-chip mat-information
  queues and ACT-enqueue, PRE-enqueue and ACT-dequeue. The ordinary DDR C/A
  interface cannot simply carry all fine-grained mat-selection information
  with an ordinary ACT; MIMDRAM communicates that information through the
  additional mechanism. Its evaluated queue capacity is eight. These source
  facts do not mandate an explicit simulator queue.
- **Accepted project contracts:** [Gate B](mimdram-addressing-geometry-and-payload.md)
  supplies resolved geometry/ranges; [Gate C execution](mimdram-movement-execution-ownership-and-device.md)
  supplies occurrence association, range-local state, physical ownership and
  recovery. The abstraction above is the user's project choice, not a source fact.
- **Implementation evidence:** the prior `dram/pud_target_queue.*` and
  Device/controller setup, PRE pairing and successor mechanics are retained
  at Git revision `0ce6922`. Current
  [Device dispatch](../../../src/ramulator/dram/device.cpp) and
  [controller issue](../../../src/ramulator/controller/controller_base.cpp)
  consume the validated resolved occurrence association without that machinery.
- [W6 progress and baseline verification](../plans/mimdram-pud-substrate-v2-implementation-plan.md)
  record the separately authorized implementation's runtime checks and limits.
  Historical detailed-transport verification is identified separately.

Open issues

- Any future sensitivity study must explicitly select and report its transport
  fidelity; physical validation of the prior PRADA mapping remains unresolved.
