# Adding PuD Primitives to Ramulator2

This guide captures the reusable implementation methodology learned while adding the DDR4_PuD RowCopy, TRA/MAJ3, 5RA/MAJ5, and NOT primitives to Ramulator2.

It is a development playbook, not a specification for any particular PuD substrate.

> **Reuse the process, not the DDR4_PuD decisions.**
>
> Timing values, resource scope, placement constraints, state transitions, atomicity, refresh behavior, and command semantics must be re-established for each new substrate or primitive from its own references and target DRAM configuration.

The current DDR4_PuD implementation is one worked example of this methodology. Future work such as MIMDRAM-based inter-column movement may require different physical scope, resources, commands, states, and controller policies.

---

## 1. Architecture map and responsibility boundaries

A compound PuD operation crosses several Ramulator2 layers. Keep their responsibilities separate.

| Layer | Responsibility |
| --- | --- |
| Request | High-level operation identity and complete operand set |
| Memory system | Generic external-request validation; PuD operand-count and channel-routing validation; channel selection |
| Controller | Multi-command sequence progress, operand roles, request-level atomicity/eligibility, arbitration, lifecycle |
| Scheduler | Candidate selection using controller-provided eligibility/command filters; no PuD-specific knowledge |
| DRAM model | Device-visible command identities, physical phase state, prerequisites/actions, directed timing |
| Completion path | `depart`, callback, completion statistics |
| Plugin | Observation or auxiliary maintenance behavior; not the owner of the core PuD request lifecycle |
| Frontend / adapter | Future workload-to-request translation when an external workload source is selected |

Do not collapse a compound primitive into one layer merely because doing so is initially convenient.

For DDR4_PuD, one request may expand into several address-specific DRAM commands. The request therefore cannot be represented faithfully as one terminal DRAM command, and the DRAM device state should not be forced to remember request identity or operand progress.

---

## 2. Questions to resolve before implementation

Before changing code, establish the following from the reference and the intended simulator abstraction.

| Question | Why it matters |
| --- | --- |
| What is the externally submitted operation? | Defines request taxonomy and callback/statistics identity. |
| How many operands exist and what roles do they have? | Determines request representation and sequence progress. |
| Which operands are ordered semantically, and which order is only deterministic traversal? | Prevents implementation order from being mistaken for a physical requirement. |
| What lower-level actions must be independently schedulable? | Defines DRAM command granularity. |
| Which internal circuit phases remain hidden inside one command? | Avoids exposing unnecessary simulator state. |
| What placement scope, timing/resource scope, and ownership/atomicity scope apply? | These scopes may differ and must be decided separately. |
| What device-visible phases must persist between commands? | Defines the minimum state machine. |
| What work may interleave while the primitive is active? | Defines request-level ownership/eligibility. |
| How do refresh, precharge, row policy, and plugin maintenance interact with it? | Prevents maintenance from corrupting a compound sequence. |
| Which timing quantities are source facts, derived values, or project assumptions? | Keeps the timing model auditable and portable. |
| When is the resource released, and when is the request externally complete? | Prevents command completion, ownership release, and callback from being conflated. |
| Which statistics have meaningful semantics for the operation? | Avoids reusing Read/Write metrics incorrectly. |
| How will a real workload eventually construct the request? | Identifies an integration gap without prematurely designing a frontend. |

If any of these questions requires a new physical or modeling assumption, record it before implementation rather than hiding it in code.

---

## 3. Isolate an experimental DRAM substrate

When an experimental primitive changes the command/state/timing model, prefer a distinct DRAM implementation boundary instead of modifying the baseline standard globally.

DDR4_PuD used a separate generated `DDR4_PuD` standard derived from DDR4 while preserving standard DDR4 behavior.

When inheriting model definitions in Python, check whether command, state, timing, request, organization, or geometry collections are mutable. Copy inherited mutable tables before extending them; otherwise the experimental substrate can accidentally mutate the baseline standard.

Do not introduce a new generic C++ abstraction merely to avoid a small amount of duplication unless the existing architecture actually requires it.

### Validation rule

Every experimental substrate should have a regression showing that the corresponding conventional standard retains its original behavior.

---

## 4. Separate request identity from DRAM command identity

A request answers:

> What operation did the caller ask the memory system to perform?

A DRAM command answers:

> What device-visible action is issued at this point in the sequence?

These identities need not be one-to-one.

For example, DDR4_PuD keeps RowCopy, MAJ3, MAJ5, and NOT as request-level operations while representing their internal device-visible activation variants and inversion step as separate commands.

For DDR4_PuD, lower-level commands were exposed for device-visible actions that required independent scheduling and timing. A new primitive must establish its own command granularity from its reference and intended simulator abstraction.

Avoid a fake terminal command for a controller-sequenced request. Use an explicit controller-sequenced marker or equivalent representation so that the abstraction is visible in the type system.

---

## 5. Represent multi-operand requests explicitly

A compound primitive should own all operands needed for its lifetime.

Do not reconstruct operands later from one scalar address, temporary caller storage, or hidden global state.

For variable-arity operations, use request-owned variable-length storage unless the physical primitive itself imposes a fixed bound.

Keep these concepts distinct:

- operand count required by primitive semantics;
- controller queue capacity;
- host-side metadata memory used by the request representation.

A queue may reasonably count one operation as one entry even when the operation contains many operands, but that is a simulator capacity policy and must not be mistaken for modeling variable metadata storage cost.

---

## 6. Split routing validation from device-aware placement validation

Validation should live where the necessary knowledge already exists.

For the current DDR4_PuD implementation, the memory-system layer performs generic external-request validation and validates PuD operand count, channel coordinates, and same-channel routing.

The controller validates address-vector shape, hierarchy bounds, shared rank, bank group, and bank, and shared derived subarray identity.

Do not make the memory system infer detailed device geometry merely to validate a request, and do not make the controller rediscover which channel should receive the request.

### Important portability rule

Logical subarray or mat mappings are substrate-specific. For DDR4_PuD, contiguous 1024-row logical subarrays were an explicit simulator assumption. A future MIMDRAM implementation must establish its own mat/subarray/inter-column placement model from the selected reference and target organization.

---

## 7. Keep the DRAM state machine minimal

Device state should answer physical-phase questions, not high-level request-progress questions.

For DDR4_PuD, the device only needed charge-sharing and sensed PuD phase states. It did not encode which primitive was active, which operand index had been processed, how many RowCopy destinations remained, or whether a command was the final step of a particular request.

That progress belongs in the controller.

This prevents state explosion. Without request-level isolation, it is tempting to define prerequisite behavior for every conventional and PuD command from every intermediate PuD state. That quickly turns a physical phase model into a primitive-specific program counter.

The preferred pattern is:

```text
device state
    = physical phase and device legality

controller state
    = request identity, operand cursor, sequence integrity
```

Atomicity or eligibility in the controller removes many impossible competing-request cases before the device prerequisite logic ever sees them.

---

## 8. Treat prerequisites as command translation, not ownership enforcement

Prerequisite resolution answers:

> Given an eligible request, what command must issue next before its intended command can issue?

It should not be responsible for deciding whether an unrelated request is allowed to enter an active compound operation's resource scope.

If a request must be rejected because another PuD operation owns an intersecting resource, perform that eligibility check **before prerequisite resolution**.

Otherwise the prerequisite handler may be asked to interpret a command in an intermediate PuD state that the request should never have been allowed to inspect.

For scheduler-managed request buffers, the conceptual pipeline is:

```text
candidate request
    ↓
request/resource eligibility
    ↓
prerequisite resolution
    ↓
command-aware filtering
    ↓
timing readiness
    ↓
scheduler comparison
```

Keep pre-prerequisite eligibility distinct from any existing post-resolution command filter. They have different semantics.

The FIFO priority-buffer head uses its dedicated controller path: eligibility, prerequisite resolution, timing readiness, active-close protection, and then any command filter. It does not use scheduler comparison, but eligibility must still be checked before prerequisite resolution.

---

## 9. Use the controller for compound sequencing and atomicity

A multi-command PuD request needs explicit monotonic progress, such as an operand/phase cursor.

Advance the cursor only when the intended PuD command itself issues. A prerequisite command such as a preparatory `PREpb` must not advance the primitive.

When a primitive starts, retain the request as active and advance it in place until its sequence terminates. Do not repeatedly promote the request merely because later PuD commands are categorized as opening commands.

If the active request itself is sufficient to identify the owned resource scope, derive ownership from it. Do not add a second bank-owner table unless there is a genuine case that cannot be represented by the retained active requests.

### Atomicity is not timing

Do not inflate timing constraints to prevent another request from interleaving. Timing should represent modeled physical minimum spacing.

Request-level atomicity should be expressed as an eligibility/ownership rule.

```text
timing/state  → physical/device legality
eligibility   → sequence integrity
```

---

## 10. Decide resource scope and interleaving explicitly

For every primitive, decide its placement scope, timing/resource scope, and ownership/atomicity scope separately. Each may involve a bank, bank group, rank, subarray, mat, column group, bus, or another substrate-specific resource.

Then decide what may interleave outside the accepted ownership/atomicity scope and how the timing/resource scopes constrain it.

Do not assume DDR4_PuD's bank-scoped ownership applies to a future primitive. Inter-column movement may require a different scope or several resources simultaneously.

The scheduler should remain substrate-agnostic when possible. Let the controller provide an eligibility predicate based on the accepted resource model.

---

## 11. Build timing as a directed constraint graph

Do not begin with only one aggregate primitive-latency number.

First identify the independently enforced command boundaries:

```text
command A → command B
command B → command C
...
final command → next legal reuse
```

For each boundary, record whether the value is directly reported by a source, derived from reported values, inherited from the selected DRAM preset, or an explicit project assumption.

Then convert each independently enforced interval to simulator cycles using the actual target preset.

If Ramulator2 enforces each edge independently, each edge must be quantized independently. The sum of individually ceiling-quantized constraints may exceed the continuous-time aggregate.

Therefore document both continuous/reference timing and cycle-accurate simulator timing.

### Baseline-dependent values

Never import a component timing from a different DRAM configuration merely because a reference aggregate used it. Re-derive dependent quantities against the actual simulator preset when required.

### Testing rule

For every new directed timing edge, test at least:

```text
required_cycle - 1   → illegal/not ready
required_cycle       → legal/ready
```

Also test resource locality: same-resource constraints and intentionally independent resources.

---

## 12. Do not use timing to hide unresolved shared resources

A primitive may consume more than a target bank: command/address bus, activation-current window, rank-wide circuitry, mat-local interconnect, global bitline, column-selection resources, or another shared structure.

Model each accepted resource explicitly at the narrowest justified scope.

If a reference does not establish a shared-resource restriction, record that absence as an assumption or limitation rather than inventing a conservative delay whose real purpose is to serialize requests.

This is especially important when moving from DDR4_PuD to MIMDRAM-style inter-column movement, where resource sharing may differ substantially.

---

## 13. Integrate with shared schedulers conservatively

A change to a generic scheduler interface can affect unrelated DRAM standards even if only one new controller supplies the new hook.

Before changing a shared scheduler, understand all existing callers, preserve the semantics of existing filters, understand multi-pass scheduler algorithms rather than only the final selection pass, and add a regression from an unrelated existing standard if the generic path changes.

### DDR4_PuD lesson: FRFCFS-RowHit

A new pre-prerequisite eligibility filter was needed for PuD ownership.

The integration risk was applying an existing command-aware filter while constructing row-hit metadata in FRFCFS-RowHit's first pass. That changes the meaning of row-hit protection for existing users.

The corrected contract kept eligibility filtering before prerequisite resolution where required and kept existing command filtering only where it had previously affected candidate selection.

> A new generic hook must not silently change the semantic phase of an existing hook.

---

## 14. Treat maintenance interaction as a separate policy decision

A compound primitive can be corrupted by `PREpb`, `PREab`, refresh, row-policy-generated work, plugin-generated priority work, or other maintenance commands.

Do not rely only on device legality to protect the sequence if some maintenance command is independently legal in an intermediate state.

Apply the same accepted ownership/eligibility rule to maintenance candidates whose resource scope intersects the active primitive.

Also distinguish correctness from concurrency optimization.

For example, bypassing a blocked priority-head refresh to execute unrelated new work may improve concurrency, but it is a new scheduler policy. Do not add it automatically merely because it is possible.

Preserve existing controller priority semantics unless a new policy is explicitly accepted.

---

## 15. Keep provisional scheduling policy visibly provisional

Sometimes an implementation phase needs temporary scaffolding before final arbitration policy is decided.

If so, record it explicitly as provisional, localize it so it is easy to replace, do not encode it into tests as a permanent policy, and do not let it silently become a modeling assumption.

DDR4_PuD temporarily used strict pending-PuD precedence before the final lifecycle gate replaced it with an accepted mixed-traffic arbitration policy.

> Temporary execution scaffolding is acceptable only when its non-final status is explicit and its replacement boundary is clear.

---

## 16. Separate ownership release from request completion

A command sequence may stop owning a physical resource before the request should be reported as complete.

For each primitive, define separately:

```text
last command issue
resource/ownership release
device recovery complete
depart timestamp
callback
statistics completion
```

These points may coincide, but do not assume they must.

For DDR4_PuD, ownership ends at final `PREpb` issue while external completion occurs after the accepted `nRP` recovery. That choice preserves the modeled primitive service boundary without unnecessarily extending ownership.

The exact boundary is substrate-specific and may be a simulator lifecycle definition rather than a claim about earliest physical data availability.

---

## 17. Generalize delayed completion carefully

Once several request classes share delayed-completion infrastructure, do not assume insertion order equals completion order.

Different request classes may have different `depart` times. The completion path must therefore use a representation or search strategy consistent with actual departure ordering.

### Reentrant callback rule

Treat callbacks as arbitrary external code.

A callback may synchronously submit another request and mutate controller-owned containers.

Never hold an iterator, reference, or pointer into a mutable completion container across a callback unless the container contract explicitly guarantees safety.

A robust pattern is:

```text
find ready completion
    ↓
move/extract completed request
    ↓
erase it from shared container
    ↓
update completion accounting
    ↓
invoke callback
    ↓
restart search as needed
```

---

## 18. Define statistics by semantic meaning

Do not force a new PuD operation into existing Read/Write metrics merely because the counters already exist.

Ask what each metric means. If `size_bytes` has no accepted meaning for a row-wide PuD operation, do not count that operation in byte throughput.

Operation-oriented statistics are often more defensible: accepted operation count, completed operation count, end-to-end latency, and queue occupancy.

Keep isolated device timing distinct from end-to-end request latency:

```text
isolated service latency
    = first primitive command issue → accepted recovery boundary

pre-start delay
    = first primitive command issue - arrive

end-to-end latency
    = depart - arrive
```

Queueing and prerequisite work may make end-to-end latency larger than the isolated primitive timing.

---

## 19. Use plugins only for plugin-shaped problems

A plugin is appropriate when the functionality is fundamentally observing issued commands, collecting information, or injecting auxiliary maintenance or policy requests through an existing extension point.

A plugin is not a good substitute for core controller behavior when the feature requires a high-level multi-command request lifecycle, per-request operand progress, ownership/atomicity, pre-prerequisite candidate eligibility, or completion/callback semantics.

Implementing those entirely in a plugin would effectively create a second controller state machine beside the real controller.

Prefer the smallest extension to the existing controller architecture that preserves normal controller responsibilities.

---

## 20. Delay frontend design until the workload boundary is known

A request-level C++ interface can be sufficient to validate and use the PuD substrate before the real workload integration is selected.

Do not design a public multi-operand frontend or trace format merely because one will eventually be needed.

First determine the intended workload source: external simulator, execution-driven frontend, trace-driven workload, direct C++ integration, or another adapter.

Then design the smallest ingress mechanism that converts that workload representation into the already-defined PuD request.

Record the missing integration as deferred work so it is not forgotten.

---

## 21. Validation strategy

Validation should be layered.

| Test layer | Primary purpose |
| --- | --- |
| Substrate/smoke | Construction, registration, isolation from baseline standard |
| Request/routing | Operand ownership, counts, channel routing, placement rejection |
| Device state/prerequisite | Phase transitions and generic command legality |
| Device timing | Every directed boundary, `t-1/t`, resource locality, CK quantization |
| Controller sequence | Exact command/address sequence and cursor progress |
| Atomicity/maintenance | Competing requests, refresh, precharge, row policy, plugin/priority interactions |
| Scheduling regression | Existing scheduler semantics, especially when generic hooks change |
| Lifecycle | backpressure/retry, ownership release, delayed completion, callback exactly once |
| Completion regression | mixed departure ordering and callback reentrancy |
| Statistics | accepted/completed boundaries, latency, queue accounting, metric exclusions |
| End-to-end | all primitives, long/variable arity, mixed traffic, cleanup, final completion |
| Usability | supported public interface, reproducible configuration, trace/callback interpretation |

Do not duplicate lower-level tests in end-to-end tests. End-to-end coverage should connect layers and exercise interactions that isolated tests cannot.

If a shared generic path changes, run an unrelated-standard regression that uses that path.

---

## 22. Lessons learned from DDR4_PuD

| Problem or risk addressed | Root cause | Reusable rule |
| --- | --- | --- |
| PuD could not start from a conventionally opened bank | Initial device model considered only isolated closed-bank starts | Test the new primitive in realistic mixed traffic; define preparatory prerequisites without advancing primitive progress |
| Ownership filtering after prerequisite resolution was unsafe | Ineligible commands could reach prerequisite handlers in PuD intermediate states | Perform request/resource eligibility before prerequisite resolution |
| FRFCFS-RowHit behavior could change for existing standards | A new filter was applied in the wrong scheduler pass | Preserve semantic placement of existing hooks; audit all passes/callers of shared schedulers |
| Phase 6 used provisional strict pending-PuD precedence | Final mixed-traffic arbitration had not yet been accepted | Mark scaffolding as provisional and resolve mixed-traffic scheduling explicitly |
| FIFO completion assumption failed | Reads and PuD requests can have different delayed-completion times | Do not assume insertion order equals departure order |
| Callback could invalidate the completion iterator | Arbitrary callback code can synchronously re-enter request admission | Remove/extract from mutable containers before invoking callbacks |
| Reference aggregate timing did not match selected preset `nRP` | Reference and simulator baseline component timings differed | Use the actual target preset and re-derive dependent timing quantities |
| Device-state-only sequencing would become complex | Physical phase and request progress are different abstractions | Keep minimal physical state in the device and sequence progress in the controller |
| Timing could have been abused to enforce atomicity | Serialization and physical delay are easy to conflate | Use eligibility/ownership for sequence integrity and timing only for modeled delay |
| Priority bypass looked attractive during refresh blocking | Correctness and concurrency optimization were being mixed | Preserve existing scheduling policy unless a new policy is deliberately accepted |
| The Python controller harness is test-only | Phase 9 selected `Request` through `IMemorySystem::send()` as the supported interface | Document and validate the supported boundary; keep test helpers test-only |

---

## 23. Checklist for a new PuD primitive

Use this checklist before implementation and again before declaring the primitive complete.

- [ ] Identify the primary physical/reference source.
- [ ] Define the high-level request and all operands.
- [ ] Separate semantic operand roles from deterministic traversal order.
- [ ] Define independently schedulable lower-level commands.
- [ ] Decide which circuit phases remain internal to one command.
- [ ] Define placement scope, timing/resource scope, and ownership/atomicity scope separately.
- [ ] Decide the minimum persistent device states.
- [ ] Define prerequisites and device actions for legal states.
- [ ] Decide controller sequence progress representation.
- [ ] Decide ownership/atomicity and what may interleave.
- [ ] Apply conflict eligibility before prerequisite resolution when required.
- [ ] Decide refresh, precharge, row policy, priority, and plugin interaction.
- [ ] Build a directed timing graph from source facts, derived values, and explicit assumptions.
- [ ] Quantize every enforced timing edge using the actual target preset.
- [ ] Define command-bus and other shared-resource occupancy explicitly.
- [ ] Define pending-buffer admission and mixed-traffic arbitration.
- [ ] Define resource release, `depart`, callback, and completion boundaries separately.
- [ ] Define only semantically meaningful statistics.
- [ ] Add boundary, locality, sequence, maintenance, lifecycle, and regression tests.
- [ ] Add unrelated-standard regression coverage for any generic scheduler/controller change.
- [ ] Add end-to-end validation without duplicating lower-level tests.
- [ ] Document supported public usage and current limitations.
- [ ] Record deferred workload/frontend integration rather than inventing it prematurely.

---

## 24. Applying this guide to MIMDRAM inter-column movement

Do not begin by copying DDR4_PuD's bank-scoped command/state/timing decisions.

Begin with the MIMDRAM reference and resolve, in order:

1. what the externally requested inter-column movement primitive is;
2. source and destination operand representation;
3. whether operands reside within one mat, logical mat, subarray, bank, or a wider scope;
4. which movement phases must be explicit Ramulator2 commands;
5. which interconnect, sense-amplifier, column-selection, or other resources are occupied;
6. what device-visible state, if any, persists between movement commands;
7. whether the movement must be atomic and at what scope;
8. how it interacts with ordinary commands, refresh, and existing PuD primitives;
9. its directed timing and command/resource occupancy;
10. completion and statistics semantics.

Only after these are accepted should the DDR4_PuD implementation patterns be selected for reuse.

A new primitive should reuse existing request, controller, scheduler, timing, and completion abstractions where they fit, but it should not inherit DDR4_PuD physical assumptions by analogy.
