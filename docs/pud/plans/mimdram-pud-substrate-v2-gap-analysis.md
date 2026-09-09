# MIMDRAM-based PuD substrate v2: gap analysis

Investigation snapshot: 2026-09-08. Sections 1–8 preserve the original gap
analysis. Section 9 records Gate B's accepted resolution and links its current
canonical decision. Gate A is now Accepted in the
[substrate and experiment boundary](../decisions/mimdram-substrate-and-movement-request-boundary.md);
§9.5 records Gate A and §9.6 links Gate C's acceptance on 2026-09-09.
Earlier alternatives and open A/B/C questions are investigation provenance,
not current decision gates.
This document is not an implementation plan.

## 1. Target definition and evidence boundary

For this project, a defensible MIMDRAM-based substrate would let an experiment
identify the mats and bit locations affected by computation and movement,
compose those operations without unintended data interference, and interpret
its timing results within an explicit resource/concurrency fidelity boundary.
Inputs may already be bitsliced, initialized, and allocated. The substrate needs
a placement contract, not an allocator, transposer, compiler, or GEMV generator.

Two claims must be distinguished before planning:

- **Mat-scoped functional computation with conservative timing:** selected
  locations have defined effects, while independent same-bank requests may be
  serialized. This can support correctness experiments and explicitly limited
  timing studies.
- **MIMDRAM-style independent mat execution:** independent operations on
  disjoint ranges can progress concurrently, with state, close/recovery, and
  shared-resource conflicts modeled consistently. This is needed to claim
  MIMDRAM MIMD performance fidelity; it is not established merely by adding
  a logical mat field.

These are target alternatives, not newly accepted scope. The existing combined
standard uses PRADA compute and MIMDRAM-derived movement. Calling its successor
MIMDRAM-based must continue to disclose that hybrid boundary: repository
references do not establish that MIMDRAM implements PRADA's complete
RowCopy/MAJ3/MAJ5/NOT/NOT_COPY command and timing model unchanged.

### Baseline and branch provenance

The audit fetched `origin` and verified remote `main` at
`d75944ad2f846d3888680d11cdf0309ecd463b57`, equal to local main. The remote no
longer advertises `feature/mimdram-inter-column`; its preserved tip is tag
`merged/mimdram-inter-column`, commit
`67db0e9d9db32cc37376e0e361d2cde46f80085e`. Merge `ab5b373` has parents
`158f8df` and `67db0e9`. The feature tip is an ancestor of main, and
`main..merged/mimdram-inter-column` contains no commits.

Consequently, **no audited capability is currently classified as
`Implemented only on feature/mimdram-inter-column`**. Its movement work is
already on main. The relevant comparisons are the historical feature delta
`158f8df..67db0e9` and the subsequent delta `67db0e9..d75944a`, not a proposed
merge.

The separate `feature/functional-simulator` tip `0f942a6`, based on this main,
was inspected only to establish the existing functional boundary and workload
evidence. Its files and results are not main capabilities.

### Evidence and classification conventions

Every capability finding uses one of the requested classifications:
`Already implemented on main`, `Implemented only on feature/mimdram-inter-column`,
`Partially modeled`, `Missing`, `Open project decision`, or
`Source feature but unnecessary for current GEMV substrate`.

Evidence labels have a separate meaning:

- **S — source fact:** preserved in the curated repository references.
- **D — accepted project decision:** an explicitly Accepted simulator choice.
- **I — current implementation fact:** established by source/tests at the
  stated commit; test assertions alone are not physical validation.
- **G — inference/gap:** an analytical conclusion or conditional dependency,
  not a new requirement accepted by the user.

Principal evidence used throughout:

| Key | Repository authority or implementation |
| --- | --- |
| R1 | [MIMDRAM movement technical reference](../references/mimdram-inter-column-data-movement.md), especially §§1.1–1.6, 2.4, 3, and 4 |
| R2 | [MIMDRAM geometry](../references/mimdram-geometry.md) |
| R3 | [PuD primitives](../references/pud-primitives.md) and [DDR4 PuD timing reference](../references/ddr4-pud-timing-reference.md) |
| D1 | [Substrate and movement request boundary](../decisions/mimdram-substrate-and-movement-request-boundary.md) |
| D2 | [Movement addressing, geometry, and payload](../decisions/mimdram-movement-addressing-geometry-and-payload.md) |
| D3 | [Movement execution, ownership, and Device](../decisions/mimdram-movement-execution-ownership-and-device.md) |
| D4 | [Movement timing and resources](../decisions/mimdram-movement-timing-and-resource-model.md) |
| D5 | [Compute placement](../decisions/pud-operand-placement-and-routing.md), [intermediate state](../decisions/pud-intermediate-state-representation.md), [precharge/legality](../decisions/pud-precharge-and-legality-semantics.md), and [sequencing/atomicity](../decisions/pud-controller-sequencing-and-atomicity.md) |
| D6 | [PuD timing/resources](../decisions/pud-timing-resource-and-command-bus-rules.md), [lifecycle](../decisions/pud-request-lifecycle-queueing-and-statistics.md), and [maintenance](../decisions/pud-refresh-row-policy-and-maintenance-interaction.md) |
| I1 | [Request](../../../src/ramulator/base/request.h), [placement/payload validation](../../../src/ramulator/controller/pud_request_validation.cpp), and [ingress](../../../src/ramulator/memory_system/pud_request_routing.h) |
| I2 | [Occurrence sequencing/timing](../../../src/ramulator/controller/pud_sequence.cpp), [GenericDDR](../../../src/ramulator/controller/impl/generic_ddr_controller.cpp), and [controller base](../../../src/ramulator/controller/controller_base.cpp) |
| I3 | [DDR4_PuD definition](../../../python/ramulator/dram/ddr4_pud.py), [movement definition](../../../python/ramulator/dram/ddr4_pud_movement.py), and generated [DDR4_PuD](../../../src/ramulator/dram/impl/DDR4_PuD.cpp) / [DDR4_PuD_Movement](../../../src/ramulator/dram/impl/DDR4_PuD_Movement.cpp) |
| I4 | [Device](../../../src/ramulator/dram/device.cpp), [node](../../../src/ramulator/dram/node.h), and [command handlers](../../../src/ramulator/dram/commands/) |
| H1 | [Original movement gap analysis](../mimdram-inter-column-gap-analysis.md) and [completed movement implementation record](mimdram-inter-column-movement-implementation-plan.md) |
| H2 | [Completed compute implementation record](ddr4-pud-primitives-implementation.md) and [current user guide](../ddr4-pud-user-guide.md) |

Current Accepted canonical movement decisions take precedence over historical
gates in H1 and their Superseded predecessors. Older compute decisions contain
forward references to gates subsequently resolved by D5/D6; those references
do not reopen completed choices.

## 2. Current-main capability inventory

### Compute and request infrastructure

**Already implemented on main — I, D (I1–I4, D5/D6, H2).** DDR4_PuD supports
five request-level operations; DDR4_PuD_Movement inherits all five:

| Primitive | Issued sequence | Isolated latency through final recovery |
| --- | --- | --- |
| RowCopy, D destinations | `A_S*(src) -> A(dst0) -> ... -> PREpb` | `40 + 5*D + 16 CK` |
| MAJ3 | `A*(x) -> A(y) -> A_S(z) -> PREpb` | `66 CK` |
| MAJ5 | `A*(v) -> A(w) -> A(x) -> A(y) -> A_S(z) -> PREpb` | `76 CK` |
| NOT | `A_S*(src) -> N -> PREpb` | `99 CK` |
| NOT_COPY | `A_S*(src) -> N -> A(dst) -> PREpb` | `104 CK` |

Here `A`, `A*`, `A_S`, and `A_S*` denote the corresponding `ACT_PUD*`
identities. These are PRADA-derived/project-calibrated cycles at DDR4_2400R,
not MIMDRAM mat-selective timing measurements. NOT_COPY reuses commands and
adds the `N -> ACT_PUD` timing edge; it is not a new circuit command.

Ordered operands are request-owned final device-visible
`[Channel, Rank, BankGroup, Bank, Row, Column]` vectors. Placement requires one
channel/rank/bank-group/bank and derived subarray (`row / 1024`). Compute
Column values are retained without operation semantics; compute `size_bytes`
passes the existing transaction-size ingress rule but does not select lanes.
Copy-safe occurrence history, prerequisite-safe progress, backpressure, delayed
completion, and per-operation statistics already exist.

**Missing — I, G (I1–I4).** None of these five compute requests has a supported
compute mat-range contract. Movement metadata is consumed for movement
validation/accounting, not for inherited compute targeting. Compute handlers
change a single Bank phase (`PuDChargeSharing` or `PuDSensed`); they do not
retain operand rows in mat-local state or operate on stored bits. The supported
placement is subarray-constrained, but execution state, timing, and ownership
are bank-wide. This is effectively unselected row computation with a bank
conflict domain, not evidence of physically computing every row in a bank.

### Movement and integration

**Already implemented on main — I, D (I1–I4, D1–D4).** The separate combined
standard supports LC-MOV/GB-MOV, typed logical-mat metadata, exact moved-bit
accounting, movement commands/states, local plus Device timing, ownership,
callbacks, and maintenance protections. Section 3 separates their fidelity.

**Partially modeled — I, D (D3/D4, I2/I4).** Movement mat selection exists in
retained requests, while Device calls still receive one command and one
ordinary address vector. Bank state contains no mat identity, active row per
mat, HFF values, or link identity. All PuD/movement requests reserve their whole
flat bank from first activation to terminal PRE issue. Unrelated banks can
progress during timing gaps; disjoint ranges of the same bank cannot.

**Already implemented on main — I, D (I2, D3/D6).** Terminal PRE issue retires
the sequence and releases ownership; `depart = terminal_PRE + nRP` determines
callback and completion accounting. Completion extraction precedes callbacks
and handles departure reordering/reentrancy. This is a lifecycle guarantee,
not an earliest physical data-availability guarantee.

### Functional and workload boundary

**Missing — I.** Main has no functional DRAM bit storage or PuD value
interpreter. On `feature/functional-simulator@0f942a6`,
`src/ramulator/base/pud_functional.{h,cpp}` implements a separate sequential
whole-row interpreter. Its sparse key drops Column and has no mat coordinate;
configurable vector index is the functional lane. It snapshots inputs,
copies RowCopy to destinations, destructively writes majority results to all
participants, and applies NOT_COPY to source and destination. These are facts
about that implementation, not an Accepted mat-scoped compute specification.

**Partially modeled — I, G.** That branch's
`tests/unit_tests/pud_functional_test.cpp` covers primitive values and the fixed
PRADA Table 2 two-bit ADD sequence against all 16 input pairs. It explicitly
rejects LC/GB. Its design record
`docs/pud/plans/pud-functional-simulator-minimal-design.md`, §§6–7, preserves
the unresolved `(logical mat, Column, HFF position) -> row-bit/lane` mapping
and specifies sequential interpretation. The record remains labeled Proposed;
it is not in `docs/pud/decisions/` and is not canonical Accepted authority.

**Missing — I, G.** No INT8/FP8 GEMV implementation, accepted GEMV experiment
contract, general ADD/MUL generator, or reduction macro was found in the
audited main/workload material or that functional branch. Therefore the
repository cannot establish a workload-specific need for simultaneous mat
execution or an all-in-DRAM scalar reduction. Those are Gate A questions.

## 3. Prior feature-branch capability inventory

The historical feature delta introduced 80 changed files, including evidence
and decisions; that count is not a measure of remaining implementation work.
Its substantive history is:

| Commits | Contribution | Classification at current main |
| --- | --- | --- |
| `a4bf52f` through `12fdbbf`, then `430d7e0` / `7b42f6f` | Reference/gap investigation, accepted refinements, canonical consolidation, and implementation records | Already implemented on main (documentation provenance) |
| `bd89210` | Request/capability foundation, combined standard/configuration | Already implemented on main |
| `0445642` | Movement operands, placement/selector/size validation, payload helper | Already implemented on main |
| `076c9c0` | Movement Device commands, aggregate state, legality and recovery | Already implemented on main |
| `b5a205e` | Retained controller occurrences, ownership, lifecycle | Already implemented on main |
| `0c99713` | Primitive-local readiness and scheduler/final-issue integration | Already implemented on main |
| `a8e3d3e` | Refresh, policy/plugin/trace integration and statistics | Already implemented on main |
| `67db0e9` | Request-path LC/GB latency benchmark | Already implemented on main |

### What the implementation actually represents

| Area | Verified capability and limitation | Classification / evidence |
| --- | --- | --- |
| Request semantics | One invocation per request, exactly source/destination operands; LC has one inclusive common range, GB two singleton mat IDs; `size_bytes=-1` | Already implemented on main — I, D2 |
| Movement topology | LC executes common addresses across selected mats in lockstep, including logical chip-crossing ranges without cross-chip payload transfer. GB permits only same-chip local `i -> i+1`, in the same derived subarray/bank | Already implemented on main — I, D2; lockstep and logical adjacency are project choices based on R1 |
| Commands | LC: `ACT_MOV,RD_MOV,PREpb,ACT_MOV,WR_MOV,PREpb`; GB: `ACT_MOV,ACT_MOV,RD_MOV,WR_MOV,PREpb`. Roles/operands live in occurrence descriptors | Already implemented on main — I, D3 |
| Device state | `MovementActive` and `MovementDataValid` at Bank; movement keeps `m_row_state` empty. GB's two activation intervals are represented without two active-mat row entries | Partially modeled — I, D3 |
| HFF behavior | RD establishes a validity marker; LC source PRE and destination ACT preserve it; WR consumes it. No actual HFF payload, per-mat latch enable, global-SA contents, or transfer of bits | Partially modeled — I, D3; physical retention/path in R1 |
| Timing | LC normalized issues `0,16,39,55,94,114`, recovery 130 CK; GB `0,1,39,41,59`, recovery 75 CK. GB source-ACT history is separate from latest destination-ACT history | Already implemented on main — I, D4 |
| Timing fidelity | Bank-conservative static edges plus six occurrence-local dependencies. `nRELOC=2 CK` applies FIGARO's guarded 1 ns as an explicit project assumption. No mat/link histories or mat-transport contention | Partially modeled — I, D4; aggregate source equations in R1 |
| Lifecycle/accounting | Enqueue/retry, continuous bank ownership, exact-once callback at recovery; LC bits = range length × HFF count, GB bits = HFF count. Separate LC/GB counts/latency/bits, excluded from normal byte throughput | Already implemented on main — I, D2/D3 |
| Maintenance/plugins | Rank-scoped AllBank refresh; queued-before-acquisition refresh wins, active movement defers intersecting maintenance; Open/ClosedCAP support; AQUA/RRS rejected for movement; observations remain command-level | Already implemented on main — I, D3 |
| Observability | Text/binary/live command traces retain command/cycle/address/type/source; omit mats, payload, unique request identity, and completion events | Partially modeled — I, D3 |

LC width and HFF configuration change moved-bit accounting, not command count
or latency. Support for positive HFF overrides is tested software behavior,
not evidence validating arbitrary physical organizations.

### Reuse and stale assumptions

**Already implemented on main — I, G.** Reuse is evaluation of existing main
components, not cherry-picking the old tip. Request-owned operands, explicit
classification, occurrence roles/history, local-readiness integration,
prerequisite-safe progress, delayed completion, exact-bit accounting, and
negative topology tests provide useful foundations. No evidence justifies
discarding them merely because finer targeting is needed.

**Partially modeled — I, G.** Bank ownership, Bank-only phase markers, shared
PRE actions, latest-Bank timing history, and absence of mat-target data in the
Device interface are coupled to the deliberately serialized model. Relaxing
ownership alone would make independent operations overwrite one another's
state/timing context. Those mechanisms need a coherent new contract if Gate A
requires same-bank independence. Existing bank-serialization tests remain
valid baseline tests; they are not the acceptance oracle for a different scope.

**Partially modeled — I, G.** Post-feature commit `ac9ff1c`, merged by `d75944a`,
added NOT_COPY. It changed LC/GB request IDs from 6/7 to 7/8, added the fifth
compute statistic slot, updated capability checks and generated definitions,
and added `N -> ACT_PUD`. Old four-compute/six-total descriptions and numeric
request-ID assumptions must not be restored. Old trace files with numeric
types need their producing revision to be interpreted correctly.

### Validation evidence and limits

**Already implemented on main — I.** Inspected validation includes
[Device state/timing tests](../../../tests/device_timings/test_ddr4_pud_movement.py),
the GenericDDR [placement tests](../../../tests/controller_scheduling/GenericDDRController/test_movement_request_validation.py),
[ownership](../../../tests/controller_scheduling/GenericDDRController/test_movement_ownership.py),
[local timing](../../../tests/controller_scheduling/GenericDDRController/test_movement_local_timing.py),
[lifecycle](../../../tests/controller_scheduling/GenericDDRController/test_movement_lifecycle.py),
[refresh/row policy](../../../tests/controller_scheduling/GenericDDRController/test_movement_refresh_row_policy.py),
[statistics](../../../tests/controller_scheduling/GenericDDRController/test_movement_statistics.py),
[plugin compatibility](../../../tests/controller_scheduling/GenericDDRController/test_movement_plugin_compatibility.py),
[trace visibility](../../../tests/controller_scheduling/GenericDDRController/test_movement_trace_visibility.py),
inherited compute/occurrence tests, and
[the movement microbenchmark](../../../examples/mimdram_movement_microbenchmark.cpp).
Assertions cover state transitions, exact edge boundaries/timelines, invalid
placement, metadata retention, recovery, maintenance, and unrelated-bank work.

**Partially modeled — I, G.** State-only Device tests intentionally omit some
controller-local delays; they are not complete legal request timelines.
Movement tests/benchmarks validate the accepted simulator model and payload
counts, not destination bit values, preservation of unselected mats, physical
latch behavior, arbitrary routing, reduction correctness, or MIMD throughput.
H1 records broad regression assertions passing, but also an unresolved
post-pytest allocator-finalization abort after 439 controller tests. This audit
does not reclassify that historical process failure as a clean suite exit or
claim it is fixed on current main. No runtime suites were rerun for this
documentation-only investigation.

## 4. Source-to-implementation capability matrix

Each row distinguishes the source description from the project's representation.

| Capability | Preserved source evidence | Main implementation / gap | Classification |
| --- | --- | --- | --- |
| RowCopy/MAJ3/MAJ5/NOT/NOT_COPY sequences | R3 describes PRADA behavior; R1 demonstrates mat-targeted TRA, not all five PRADA mechanisms | All five sequences exist, without compute mat targets (I); selected-range applicability is unaccepted (G) | Partially modeled |
| Physically contiguous selected compute range | R1 §1.1–1.2: mat selector and shared ACT–PRE sequence/state for a range (S) | No compute range contract or physical-contiguity proof (I/G) | Missing |
| Logical movement mat namespace | R1: chip/mat encoding; physical namespace scope incompletely specified (S) | D2 adopts 128 IDs per derived-subarray context; validated metadata exists (I/D) | Already implemented on main |
| Mat isolation and row-decoder latches | R1 §1.2: preserve local row address while another mat is activated (S) | No mat-local active address/phase or equivalent independently retained Device context (I) | Missing |
| Range ownership and independent execution | R1 §1.2: scoreboard and multiple engines for available disjoint ranges (S) | One owner per flat bank; unrelated-bank overlap only (I/D) | Missing |
| Selected-range PRE/recovery | R1: fine-grained execution and PRE transport; exact movement PRE scope unresolved (S) | Terminal PRE closes Bank aggregate, source LC PRE preserves only validity marker (I/D) | Partially modeled |
| LC local path | R1 §1.4: source ACT/RD/PRE, retained HFFs, destination ACT/WR/PRE (S) | Phase sequence and retention condition exist; transferred bit identities/values do not (I) | Partially modeled |
| GB neighboring path | R1 §1.5: neighboring global-SA mux and overlapping activations (S) | Same-chip directed singleton subset; logical adjacency is D2, values absent (I/D) | Partially modeled |
| Wider/non-neighbor/cross-chip GB | R1 §§3–4: wider pairing and non-neighbor routing unresolved; depicted path is within a chip | Intentionally unsupported (I/D); workload need not established (G) | Open project decision |
| Column/HFF-to-cell mapping | R1 describes four-bit transfer; does not preserve a complete selector decode (S) | D2 deliberately opaque Column; no functional selection/alias map (I/D) | Open project decision |
| Payload width | R1: evaluated four HFFs per mat (S); LC range total is an inference | Configured HFF count and exact LC/GB bit totals (I/D) | Already implemented on main |
| LC/GB latency structure | R1: `2*(tRAS+tRP)+tRELOC+tWR` / `tRAS+tRELOC+tWR+tRP` (S) | 130/75 CK project graphs reproduce aggregate structure, not physical circuit validation (I/D) | Partially modeled |
| Mat-information transport | R1 §1.2: eight-entry per-chip queue and enqueue/dequeue variants (S) | D4 T3 abstraction; no queue, transport pressure, or exact C/A model (I/D) | Partially modeled |
| GB+ADD then LC+ADD reduction | R1 §1.6: combine into one mat, then adder tree to four elements (S) | Requests can name individual moves; no mat-local ADD composition/mapping/reduction stream (I/G) | Missing |
| Scalar `4 -> 1` reduction | R1 §4.9 explicitly unresolved | No supported source mechanism; output/finishing boundary undecided (G) | Open project decision |
| Maintenance already in progress | R1 §1.2: AAP/AP waits and command order is preserved (S) | Recovery constraints plus admission/ownership policy protect sequences (I/D) | Already implemented on main |
| Refresh deferral/retention fidelity | R1 does not specify movement deadlines/preemption (S evidence limit) | No postponement bound or retention model (I/D) | Partially modeled |
| Minimum bitsliced placement interface | R1 identifies rows, columns, ranges, precision-dependent movement (S) | No common compute/movement lane identity or physical mapping (I/G) | Open project decision |
| ISA-level `bbop_mov` lowering/control stack | R1 §1.3 gives arrays, indices, size, precision and LC/GB selection (S) | Direct Request submission bypasses this layer by D1 | Source feature but unnecessary for current GEMV substrate |

## 5. Concrete gaps and dependencies

### 5.1 Compute granularity

**Missing — I, G.** RowCopy, MAJ3, MAJ5, NOT, and NOT_COPY cannot select a mat
range on either standard. Same-derived-subarray validation is not mat selection;
neither Column nor request byte size supplies the missing compute target.

For the same primitive to operate on a physically contiguous selected range,
the missing contract must establish the range's location/physical interpretation,
common row operands and lockstep effect, the participating bits within each
mat, destructive/source-preserving effects, and preservation outside the range.
Selection must reach every activation, sensing/inversion, and final close
action, with enough retained context that another range cannot change its
meaning. A literal Mat hierarchy is one representation alternative; internal
range/mat state is another. Neither follows automatically from R1.

**Open project decision — S, D, G.** R1 supports fine-grained TRA and range
selection; R3 supports the five PRADA sequences. Their physical compatibility,
mat-scoped phase timings, and range-width scaling are not established by their
coexistence in the repository. Reusing PRADA as the compute backend is a possible
explicit hybrid modeling decision, not a newly verified MIMDRAM fact. D1
currently preserves inherited compute semantics and leaves mat-selective
compute open. Any refinement must respect that baseline boundary.

### 5.2 Mat state, selector, and resource ownership

**Missing — I, G.** No mat-level active/state information exists in main:
`DRAMNode::m_state` is one Bank phase and `m_row_state` is keyed by Row without
Mat. Compute does not populate per-operand active-row entries; movement
deliberately leaves the row map empty. Controller operands/history describe
progress, not independent mat-local row-decoder latches.

**Partially modeled — S, I, D.** LC ranges and GB endpoints retain semantic
selection in the controller (D2), but the mat isolation transistor, local
decoder-latch retention, selector effects on Device state, and selection for
RD/WR have no executable representation. The source's shared state for one
lockstep range does not imply a single state for every independent range in
the bank. Exact LC/GB queue/column-command target transport remains missing
source evidence (R1 §4.7–4.8), not permission to assume ACT alone selects all
subsequent RD/WR targets.

**Partially modeled — S, D, I.** R1's general transport uses a two-cycle
`ACT-enqueue` (ACT then range communication), `PRE-enqueue` (PRE with range
communication), and `ACT-dequeue` (ACT consuming queued mat information).
Selection information must be available before the corresponding activation
selects mats. Main models none of these command variants or the eight-entry
per-chip queue; D4's T3 abstraction retains semantic targets without transport
pressure or transport-specific C/A occupancy. This is an omitted cost, not a
claim of zero-cost physical selection. The source does not give the exact
movement-specific enqueue/dequeue schedule.

**Open project decision — G.** Independent-range execution needs compatible
state, resource ownership, and legality together. Relaxing the bank owner while
retaining Bank-only states or latest-Bank timing cannot distinguish two LC
payload conditions or two independent compute phases. State could be retained
per mat or shared per active lockstep range; resource conflicts may extend
beyond selected mats. Exact per-mat storage and a physical scoreboard replica
are not unconditional requirements.

### 5.3 Precharge and completion

**Partially modeled — I, D, G.** Compute's final `P` is explicitly modeled as
whole-Bank `PREpb`, clearing Bank row state. Movement terminal `PREpb` likewise
sets the Bank aggregate to Closed and clears its row map; the LC source
`PREpb` leaves `MovementDataValid` unchanged. It does not record which source
mat rows closed while other mat rows remain active. D3 explicitly avoids
claiming that its Bank-level movement PRE is a physical whole-bank precharge.

This is sufficient for the accepted exclusive-bank model. It cannot support
independent active ranges: completing one range must preserve the other
range's active/retained conditions and constrain recovery at the appropriate
resource scope. Preparatory close, LC source close, terminal close, ordinary
PRE, and rank-wide PRE/refresh need distinguishable target effects. Whether
those effects use new commands, target metadata, or another abstraction is
open. The exact physical movement PRE scope still requires evidence or an
explicit project abstraction (R1 §4.6).

**Already implemented on main — I, D.** Ownership release, recovery, and
callback are already distinct. Preserve that conceptual separation when
deciding range-local completion; no new callback API is inherently required.
Existing delayed callbacks do not define when a future functional interpreter
must expose intra-request intermediate values.

### 5.4 LC-MOV and GB-MOV substrate

**Partially modeled — I, G.** The phase/timing machinery in §3 is a usable
bank-conservative movement model, not a functional movement substrate yet.
It lacks identified source/destination bits and preservation/alias semantics.
The HFF validity marker correctly expresses the accepted retention condition
but cannot prove what was copied. A sequential request-level value interpreter
could represent the final effect without simulating every electrical HFF phase;
explicit per-HFF temporal contents become necessary only if the chosen model
exposes interference or intermediate values that depend on them.

**Open project decision — S, D, G.** Keep singleton directed GB as an available
initial topology; do not infer a reverse path, wrapping edge, cross-chip bus,
all-to-all crossbar, wider paired ranges, or automatic multi-hop routing.
Larger reductions require either placement compatible with accepted paths or
an explicitly justified routing/finishing boundary. Repeated forward hops are
a possible later orchestration choice with scratch/ordering implications,
not an already specified source protocol.

**Partially modeled — I, D, G.** Current movement timing also omits new
`tRRD`/`tFAW` or activation-current constraints, ordinary same-bank `nRC`
between GB activations, external-DQ/CAS/turnaround occupancy, and additional
shared rank/channel movement resources (D4, I3). Those omissions are explicit
fidelity limits, not physical exemptions inferred from PRADA or MIMDRAM.
The 130/75 CK checks do not validate contention when independent ranges run.

### 5.5 Movement addressing and functional mapping

The snapshot below records the original gap; see §9 for the subsequent proposal
for a substrate-owned internal geometry mapper shared by compute and movement.

**Open project decision — D, I, G.** The already-discovered Column gap is
unchanged. Precisely what is defined and undefined is:

| Item | Defined today | Still undefined for functional movement |
| --- | --- | --- |
| Logical mat | D2: 7-bit ID, chip = ID / 16, local mat = ID % 16, namespace per derived subarray | Complete physical map, range physical contiguity, reconciliation with full device geometry |
| Row | Full Bank-row coordinate; derived subarray/local row by division/remainder at 1024 | Physical DDR4 address decoding; relation of functional row storage to individual mats |
| Column | Independent source/destination opaque selectors, structurally `0 <= Column < 1024` | Decode into physical columns/bitlines/HFF groups, ordering, stride, alignment, equivalence to ordinary external Column |
| HFF position | Configured count (`hffs_per_mat=4` baseline) determines width | Which cell/lane each HFF position selects, and source-to-destination position correspondence |
| Payload | LC range length × HFF count; GB one HFF width; counted in bits once | Actual ordered bits, untouched destination bits, source preservation and snapshot effects when locations overlap |
| Aliasing | No movement alias model; equal or unequal selectors both accepted | Whether distinct selectors alias, partial overlap, same-location behavior, any permutation across endpoints |
| Bitsliced lane | Functional branch vector index identifies a lane across its bit-plane rows | Common identity relating those indices to mats, Column selectors, HFF positions, and movement destinations |

The configured 1024-selector namespace is not evidence of 1024 independent
four-bit positions in a 512-column mat. Even the count `512 / 4 = 128` would
describe nonoverlapping groups only under an additional mapping assumption;
it does not authorize restricting selectors to 128, dividing Column by four,
using modulo, or inventing aliases. R2's 64-byte line distribution also does
not supply the missing decode. No mapping is selected here.

### 5.6 Vector reduction support

**Missing — S, I, G.** R1 §1.6 describes local additions in two mats, repeated
GB-MOV of the first partial vector into temporary rows of the second, then
ADD there. LC-MOV plus ADD subsequently reduces the one-mat vector (e.g.,
512 elements) to four elements. The number of movements depends on precision:
four moved bits are not four complete INT8/FP8 values. A bit-plane/lane map
and the represented partial-sum precision are needed before transfer counts
can be derived.

Main can express an individual permitted GB or LC invocation with chosen
row/selector addresses. It cannot yet express “ADD only in this mat” through
its inherited compute requests, or identify which lanes LC realigns for the
adder tree. No ADD request is required merely because the paper uses ADD:
arithmetic may be a future macro over accepted primitives. The functional
branch's fixed two-bit ADD fixture demonstrates limited composition, not an
INT8/FP8 adder or the MIMDRAM reduction path.

The **substrate** needs addressable selected compute, defined movement effects
and supported connectivity, preservation of other locations, and a usable
completion/dependency boundary. The **future macro** owns bit precision,
arithmetic order, carry/accumulator representation, scratch use, repeated
transfers, and reduction scheduling. Main has no arithmetic dependency graph;
per-request sequencing is not a cross-request dependency guarantee. Submitting
a whole dependent stream to an oldest-ready scheduler must not be assumed to
match a sequential functional interpreter. Existing callbacks can support
ordered submission, but the future workload contract must say how dependencies
are respected.

**Open project decision — G.** Decide whether experiments terminate at partial
outputs, four outputs per reduction, or a scalar, and where any final combine
happens. R1 explicitly leaves `4 -> 1` unresolved. A scalar entirely within
DRAM would need additional source evidence or a declared project extension;
host finishing must not be silently inserted. Likewise, accepted GB does not
connect logical chips, so module-wide reduction needs an explicit boundary.
The exact FP8 format, rounding, and accumulation arithmetic belong to future
numeric/macro work; only their consequences for locations, widths, dependencies,
and claimed reduction endpoint constrain this substrate investigation.

### 5.7 MIMD and concurrency

**Missing — S, I.** R1 §1.2 preserves MIMDRAM's independent bbop scheduling:
range availability scoreboard, assignment to free microprogram engines,
concurrent engine progress, and release of mats on completion. Mat isolation
and decoder latches allow different operations in a subarray to retain their
own activation context. Main permits none of this within one bank, including
when requests use different derived subarrays or disjoint movement ranges.

**Open project decision — G.** For data-independent operations with correct
target isolation and explicit dependencies, serial execution can preserve
functional results. It does not preserve throughput, utilization, scheduling
interference, or all workload latency of MIMDRAM MIMD. There is no repository
GEMV workload showing that simultaneous disjoint-range progress is required
for correctness. Bank-wide *effects* and absence of lane mapping cannot be
excused by serialization; bank-wide *reservation* may be an explicit performance
abstraction. Gate A must decide what the experiments need to claim.

R1 expressly does not define LC/LC, GB/GB, LC/GB, or movement/compute pairwise
shared-resource conflicts. Disjoint mat IDs alone therefore do not prove
movement concurrency is legal. True same-cycle command issue is also not
implied by overlapping operation intervals or GB's source equation.

### 5.8 Maintenance and refresh

**Already implemented on main — I, D.**
[AllBankRefresh](../../../src/ramulator/controller/refresh/impl/all_bank.cpp)
generates rank-scoped refresh for both standards. GenericDDR preserves active
precedence, FIFO priority-head blocking, and protection before prerequisite
resolution. Refresh queued before movement acquisition blocks its start;
refresh generated during ownership waits until terminal PRE and applicable
recovery. Movement-aware PREab/REFab validation rejects conflicting aggregate
states before partially mutating banks. Inherited compute is protected by
controller ownership. Current policy is non-preemptive.

**Partially modeled — S, D, I, G.** R1 says AAP/AP waits for already-active
maintenance and operation commands preserve order. It does not define movement
refresh deadlines, pause/resume, or maximum postponement. Main has no retention
or deferral-credit guarantee; long RowCopy lists can defer refresh excessively,
and AllBankRefresh throws if priority enqueue fails. Existing periodic refresh
generation does not establish a deadline guarantee.

If ranges become independently active, rank-wide refresh/close must intersect
all affected owners and respect their recovery. That safety dependency belongs
with range ownership; it need not imply mat-selective refresh or a full refresh
redesign. Short isolated correctness/latency tests can retain their explicit
NoRefresh boundary. Longer traffic claims need a stated refresh policy and
evidence that its limitations are acceptable; a new deadline/retention model
is conditional on those claims, not imposed by this investigation.

### 5.9 Minimum data-layout boundary

**Open project decision — G.** With bitsliced inputs already allocated, the
minimum caller/substrate agreement still needs:

- the context and target mat/range of each compute operand and movement
  endpoint, including the supported interpretation of physical contiguity;
- the relation between bit-plane rows, lane identities, and selected mats,
  shared by compute and movement;
- the mapping from `(context, mat, row, Column, HFF position)` to selected
  bits, with destination correspondence and alias/preservation rules;
- initialized input/constant/scratch locations and legal placement along
  supported movement paths, without assigning who allocates them;
- an output/reduction boundary and dependency/completion contract that lets
  functional and timing consumers execute the same logical operations.

This does not require a host virtual-address map, automatic layout selection,
an allocator, a transposition engine, or an INT8/FP8 datatype in each DRAM
request. A functional lane count is not automatically a physical mat width.

## 6. Open decisions before an implementation plan

The smallest coherent set is **three coupled decision gates**. These gates
define contracts, not implementation work units. All are classified
**Open project decision — G**.

| Gate | Decision to resolve | Alternatives and key trade-offs | First consumers / authority needing refinement |
| --- | --- | --- | --- |
| **A — Experiment target and evidence/fidelity boundary** | What will INT8/FP8 GEMV results claim: functional mat-scoped execution with serialized timing, or same-bank MIMD performance? What reduction endpoint and supported placement domain are required? Is PRADA compute plus MIMDRAM targeting/movement an explicitly accepted hybrid? | Conservative serialization lowers resource-model scope but cannot claim MIMD throughput. Independent ranges require a coherent resource model. Partial/four-element outputs avoid asserting an unreferenced scalar path; all-in-DRAM scalar or broader connectivity requires evidence or an explicit extension. | Target capability checks, experiment oracles, and interpretation of performance. Refine D1 and the relevant compute authority; do not treat the functional branch's Proposed design as acceptance. |
| **B — Common mat/bit addressing and operation effects** | Define contiguous target ranges for all five compute primitives and a shared compute/movement bit identity: physical/logical mat relationship, Column decode, HFF correspondence, aliases, and preservation/destructive effects. | An explicit project mapping can make functional behavior deterministic if its evidence limits are disclosed; a physically asserted map requires missing source material. Narrowing accepted selectors or changing aliases alters D2 and compatibility. Range metadata versus another representation must be assessed without assuming a hierarchy extension. | Compute target validation and functional memory/LC/GB interpretation are the first consumers. Refine D2 and compute placement/effect authority together; retain the old whole-row baseline unless a change is explicitly accepted. |
| **C — Coherent execution, resource, and lifecycle model** | For A/B's target, decide retained mat/range state, ownership/conflicts, selector/latch abstraction, source/terminal/preparatory close effects, recovery/completion, timing responsibility, mat transport, and maintenance intersection. | Bank-conservative timing can remain an explicit abstraction if A permits it. Independent ranges require distinct state/recovery/timing contexts and justified shared-path conflicts; disjoint IDs alone are insufficient. Explicit queues/latches offer fidelity but need evidence; abstract transport must state omitted contention. Internal state and hierarchy-based representations remain alternatives. | Command targeting/actions, prerequisites, owner eligibility, timing history, and maintenance all consume this contract and must agree before executable semantics are planned. Refine D3/D4 and applicable D5/D6 boundaries; no separate refresh redesign gate unless A requires stronger deadline fidelity. |

Gate C includes timing because Bank-history edges and shared PRE cannot safely
be retained as an afterthought when ownership becomes finer. Placement,
physical resource conflicts, and reservation policy remain distinct decisions
within that gate even when resolved together.

### Missing evidence and documentation needs

These are recorded needs only; references and decisions are unchanged:

- **Missing — S evidence limit / G:** a preserved mapping or source excerpt
  relating logical mats to physical contiguous ranges and the full
  chip/subarray organization; the current source summary explicitly leaves
  that relationship incomplete (R1 §§3.6, 4.1–4.2).
- **Missing — S evidence limit / G:** column-select/HFF wiring or an equivalent
  bit-selection description sufficient to support a physical mapping,
  including endpoint bit correspondence and aliases. D2's opaque namespace
  cannot supply it.
- **Missing — S evidence limit / G:** physical support/timing evidence for
  applying all five PRADA primitives to selected MIMDRAM ranges, or explicit
  acceptance of that hybrid as a project assumption.
- **Missing, conditional on Gate A — G:** exact movement PRE/select transport,
  LC/GB shared-resource concurrency, and transport/C/A or activation-current
  evidence if those performance claims are required. FIGARO does not directly
  validate either complete MIMDRAM circuit path (R1 §§2.4, 3.1, 4).
- **Missing, conditional on Gate A — G:** a `4 -> 1` source mechanism and wider
  or non-neighbor/cross-chip routing evidence if required for the chosen final
  reduction. Their absence must not be filled with presumed hardware.
- **Partially modeled — I/G:** R2 still says mat mapping is undefined; D2 now
  establishes a logical movement namespace while leaving physical mapping
  open. H1's original “no movement” inventory and old four-compute descriptions
  are historical snapshots. Recover current capability from this baseline and
  canonical authority; no retrospective cleanup is required for this task.
- **Partially modeled — I/G:** several Accepted compute documents predate
  NOT_COPY, although its source reference, guide, source/tests, and history
  are current. Future accepted mat-scoped compute authority should cover all
  five primitives coherently instead of copying the four-operation wording.

## 7. Features explicitly excluded from the current target

These exclusions describe this investigation's proposed substrate boundary;
they do not silently settle Gate A's performance or reduction choice.

| Feature | Evidence boundary and reason for exclusion | Classification |
| --- | --- | --- |
| Full ISA/programming interface, array/index `bbop_mov` lowering | R1 §1.3 preserves this source feature. Final device-visible requests are sufficient at the agreed substrate boundary (D1); full ISA emulation is unnecessary | Source feature but unnecessary for current GEMV substrate |
| Full microprogram/control-unit implementation | R1 describes engines and a mat scheduler. Their required externally visible behavior may be modeled without reproducing the whole control stack; independence is conditional on Gate A | Source feature but unnecessary for current GEMV substrate |
| Compiler integration and programmer-transparent end-to-end software | Not needed with explicit prebuilt request streams. Detailed compiler mechanisms are **not preserved in the repository references**; no specific compiler design or source behavior is asserted here | Source feature but unnecessary for current GEMV substrate (candidate feature; detailed source evidence missing) |
| Automatic transposition and transposition initialization | User permits already-bitsliced inputs. Detailed MIMDRAM initialization/transposition mechanisms are **not preserved in the repository references**; their mechanics/costs cannot be claimed from this audit | Source feature but unnecessary for current GEMV substrate (candidate feature; detailed source evidence missing) |
| Allocator, automatic scratch placement, host-address integration | Caller may supply initialized locations. Only the minimum contract in §5.9 is needed; no source-backed allocator requirement is established | Open project decision (excluded from this task's substrate scope) |
| Full INT8/FP8 ADD/MUL/GEMV macro library and numerical policies | Future consumers of the substrate; exact arithmetic and schedules are separate from DRAM operation support | Missing (future macro work, not a substrate implementation requirement) |
| Energy/area replication, circuit simulation, other DRAM standards | No PuD/movement energy model is supplied by current main; the user guide and prior scope do not claim one. New quantitative energy or physical claims would need their own evidence | Missing (outside the current functional/timing substrate objective) |

Explicit mat queues, finer resource models, and scalar finishing are not blanket
exclusions: their necessity follows from Gate A. Conversely, choosing MIMD does
not automatically require a compiler, true same-cycle multi-command issue,
per-transistor simulation, or a full refresh redesign.

## 8. Recommended decision order

1. Resolve **Gate A** first: name the experiment claims, hybrid-compute boundary,
   reduction endpoint, and required placement/concurrency envelope. This decides
   which missing evidence is actually blocking.
2. Resolve **Gate B** next: settle the common mat/bit identity and selected
   operation effects before extending functional movement. Payload width alone
   is insufficient.
3. Resolve **Gate C** against A/B as one consistent state/ownership/close/timing
   contract, including the minimum maintenance interaction. Reassess accepted
   T3 and bank-conservative assumptions only to the extent this target needs.

After user acceptance, record refinements in the existing coherent canonical
decisions where they belong and preserve their evidence limitations. A
trustworthy implementation plan can then be written without reconstructing
authority from old exploratory gates. No phases, work units, or implementation
steps are selected by this document.

## 9. Gate B: common internal geometry and address mapping

**Accepted, 2026-09-08. Gate B is closed.** The
[canonical addressing/geometry decision](../decisions/mimdram-addressing-geometry-and-payload.md)
records the replaceable generic contract and the selected
**MIMDRAM-DDR4_8Gb_x8 modeled placement profile v1**. Chip-major striping is an
explicit simulator convention; byte-lane is a considered, unselected
alternative. No physical vendor wiring claim or Gate C decision follows.

One physical/layout placement origin feeds paired external/internal views
through one canonical CellID authority. The generic contract requires neither
one scalar byte address per PuD operand nor an arithmetic G/B identity.
The selected x8 instance produces `G = B` from its complete placement
convention. Source investigation is retained below; §9.4 points to the
current Accepted authority rather than maintaining a second specification.

**Gate B question:** what is the minimum replaceable address/geometry mapping
contract that derives conventional DRAM and MIMDRAM internal mat/column
coordinates from that common source, so timing, mat-level ACT/RD/WR, movement,
and future functional simulation refer to the same physical data?

### 9.1 Evidence: organization and movement selectors

R1/R2 remain the curated evidence base. The
[MIMDRAM author-hosted paper](https://ghose.web.illinois.edu/papers/24hpca_mimdram.pdf)
was also checked against §§2.1, 4.1–4.2, 6.1, 6.3 (including footnote 13),
Table 2, and §8.5.
The following distinctions matter:

| Item | Established evidence and its limit |
| --- | --- |
| Chip/mat counts | R2 and Table 2 report DDR4-2400, one channel, eight chips, four ranks, 16 banks/rank, an 8 KiB row, 16 mats/chip, 1K rows/mat, and 512 columns/mat. These are evaluation parameters, not universal DDR4 geometry. |
| HFF width | R1 §1.4–1.5 and paper §4.1 footnote 5 establish the evaluated assumption of four one-bit HFFs per mat. Table 2 itself does not list HFF count. One mat contributes four bits per described internal movement transfer. |
| Logical IDs | R1 §1.1: seven bits, with three chip bits and four mat bits; one operation names an inclusive contiguous range. This does not enumerate every physical mat in the entire multi-rank module. |
| Subarray scope | R1 §§1.1–1.2, 3.6 distinguish the general 8–16 mats/subarray description from the evaluated logical organization. The 128-bit per-subarray scoreboard supports the adopted subarray-scoped namespace, but does not supply a complete physical address map. |
| Cache-line distribution | R2 records distribution over all 128 mats. Paper §6.3 footnote 13 explicitly gives four bits per mat, the lowest four line bits in chip 0/mat 0, and the highest four in chip 7/mat 15. It does not provide the full cell-selector or DQ/burst wiring map. |
| x8 qualification | The inspected MIMDRAM configuration text says eight chips, without explicitly labeling that entry x8 or resolving its module/rank chip-count shorthand. R1 §2.1 separately preserves FIGARO's x8, 64-bit-per-chip internal buffer and eight-chip rank example. This project's x8 rank interpretation is independently explicit in the Ramulator preset; it should not be misattributed to MIMDRAM Table 2. |

**Derived arithmetic:** the cited MIMDRAM example gives
`8 chips × 16 mats/chip × 4 bits/mat = 512 bits = 64 B`, with
`16 × 4 = 64 bits = 8 B` contributed by each chip. Combining it with this
project's x8/prefetch-8 organization is consistent with `8 × 8 = 64` internal
bits per chip. The x8 output width is not the per-mat HFF width. The four-rank
evaluation parameter does not multiply a single line's payload by four.

For **LC-MOV**, `column_src` selects four source local-row-buffer bits through
column-select logic into the same mat's HFFs; those HFFs retain the payload
across source PRE. `column_dst` connects the HFFs to the selected destination
local sense amplifiers and cells. For **GB-MOV**, source selection feeds the
source HFF/global-SA set; the neighboring-SA path feeds destination HFFs and
the destination-selected cells. Thus one selector identifies an HFF-width
payload in the worked geometry, not one cell bit or a full row. See R1
§§1.4–1.5 for the source mechanism.

Neither R1 nor the checked paper provides a complete numeric selector decode,
the ordered cell columns attached to each HFF for every selector, or a numbered
source-to-destination wire correspondence. LC reuses the retained HFFs; GB
copies the four-bit value through the neighboring sets. This supports an
ordered payload-copy abstraction, but an explicit convention is still needed
to give each payload position a cell identity.

**Not source-established:** the number of distinct selector encodings,
complete group coverage, disjointness, partial overlaps, aliases, selector
stride/alignment, or an arithmetic relation to Ramulator Column. If 512 cells
are partitioned exhaustively into disjoint four-cell groups, there are
`512 / 4 = 128` groups. That count is conditional arithmetic, not a recovered
circuit decode. No physical `Column / 4`, `Column % 128`, or alignment rule is
inferred here.

**Higher-level placement evidence:** R1 §1.3 and MIMDRAM §6.1 describe the
control unit deriving movement mat ranges from array locations, element
indices, and movement size, then choosing LC-MOV or GB-MOV. In §6.3, bbop
addresses undergo virtual-to-physical translation. The `pim_malloc` allocator
uses DRAM organization and the controller-provided interleaving scheme to
identify physical regions in particular subarrays/mats and align related
objects. Footnote 13 relates mat interleaving to chip organization. These
facts support a common physical-location model, but do not specify this
simulator's address-bit decode or require two particular request fields.
[Source: MIMDRAM §§6.1, 6.3](https://ghose.web.illinois.edu/papers/24hpca_mimdram.pdf).
The allocator/compiler/transposer themselves remain outside this proposal.

### 9.2 PRADA comparison and hybrid boundary

R3 establishes sequential activation/charge sharing, sensed RowCopy, temporal
in-place NOT, and NOT-and-copy with the source still activated. It does not
preserve PRADA's array-mat organization or HFF count. The **eight array-mats per
subarray** example identified in this task cannot be independently verified
from the supplied repository excerpts: no paper PDF was found locally, and
the [PRADA publisher paper](https://doi.org/10.1145/3676536.3676771) could not be
retrieved. The needed evidence is its organization figure/text and the
associated column-select/internal-I/O description. This is an evidence gap,
not a finding that PRADA has no such description.

Even accepting the eight-mat example as given, it does **not** establish eight
HFFs per mat. **Conditional arithmetic only:** if those eight mats contribute
equally and simultaneously to one 64-bit chip-internal transfer, each supplies
eight bits. Equating that contribution with eight one-bit HFFs further assumes
one HFF-held bit per transferred position in that transfer, with no different
staging or multiplexing. None of those datapath conditions is established by
the curated PRADA material. Do not transplant this hypothetical width into
MIMDRAM's four-HFF profile.

The proposed compute effects in §9.5 apply PRADA primitive behavior to
MIMDRAM-shaped mat regions. Accepting that hybrid and its timing fidelity
remains Gate A; geometry does not establish circuit compatibility or authorize
PRADA timing reuse for arbitrary selected ranges.

### 9.3 Current Row/Column semantics and exact mismatch

Current source was checked at `d75944a`:

- [DDR4 organization](../../../python/ramulator/dram/ddr4.py), inherited by
  both PuD standards: `DDR4_8Gb_x8` has DQ width 8, channel width 64, default
  one rank, four BankGroups × four Banks, 65,536 Rows/Bank, and 1,024 Columns.
  Internal prefetch is eight. Capacity arithmetic is
  `16 × 65536 × 1024 × 8 = 8 Gibit/chip`; one chip-row contains 8,192 bits
  and the eight-chip rank-row contains 8 KiB. Column here is an organization
  coordinate scaled by device DQ width, not a physical mat bitline index.
- [Transaction sizing](../../../src/ramulator/dram/dram_spec.h) gives 64 B
  for this configuration. The normal
  [channel mapper](../../../src/ramulator/memory_system/channel_mapper/impl/cache_line_interleave.cpp)
  selects Channel and removes its bits; the controller mapper then maps the
  intra-channel address. [AddrMapperBase](../../../src/ramulator/controller/addr_mapper/addr_mapper_base.cpp)
  subtracts three prefetch bits from the ten Column bits and removes the
  six-bit transaction offset. ChRaBaRoCo, RoBaRaCoCh, and MOP4CLXOR consequently
  produce **compact burst indices `0..127`**, without shifting them back by
  three. They do not emit only multiples of eight in `0..1023`. PassThrough
  does no such conversion. Thus the configured organization bound and the
  flat mapper's emitted Column domain are different even today.
- D2 and compute placement retain full Bank-row operands. Python sets
  `rows_per_subarray=1024`; [DRAMGeometry](../../../src/ramulator/dram/dram_spec.h)
  implements `subarray_id(row) = row / rows_per_subarray`. Runtime configuration
  requires a positive divisor of Rows/Bank. Accepted `local_row = row % 1024`
  is the companion interpretation, **not a current stored coordinate or C++
  local-row helper**. Current validation uses the quotient, and commands keep
  the original full Row. This yields 64 logical subarrays/Bank under the
  preset. Both quotient/remainder mapping and contiguous row grouping remain
  project assumptions, not physical DDR4 decoding evidence.
- [PuD routing](../../../src/ramulator/memory_system/pud_request_routing.h)
  and GenericDDR's special request path use final operand vectors and bypass
  ordinary channel/controller address mapping. Compute Column is retained
  without effect semantics. Movement Column is structurally bounded to
  `0..1023`, opaque under D2, and passed with each occurrence; RD_MOV/WR_MOV
  only update Bank phase markers, without decoding bits.
- [Movement validation](../../../src/ramulator/controller/pud_request_validation.cpp)
  hard-codes 128 logical mats and 16 mats/chip. Logical identity is separate
  metadata, scoped by Bank and derived subarray; Row/Column do not choose a
  mat. HFF count is already configurable, but currently changes only exact-bit
  accounting. No complete internal geometry is represented.

The organization Column, external compact burst Column, and internal mat-local
selector are different abstractions. Equal domain sizes do not establish
equal coordinate values. The mandatory identity convention is withdrawn;
the internal decode must be allowed to use information absent from AddrVec.

**Information retention verified in the current paths:**

| Path | What survives and what the final coordinates omit |
| --- | --- |
| Flat-address Request | [Request constructors](../../../src/ramulator/base/request.cpp) retain the supplied address in `addr`. CacheLineInterleave removes channel bits into `intra_channel_addr` without changing `addr`; the latter field is therefore still available after mapping. |
| Controller compaction | The mappers right-shift a local copy of `intra_channel_addr` by six for the baseline 64 B transaction. All six byte-offset bits are absent from AddrVec. The separate three-bit Column-width reduction accounts for prefetch; it is not evidence that only three original address bits were discarded. |
| Address/routing context | [Gem5PortInterleave](../../../src/ramulator/memory_system/channel_mapper/impl/gem5_port_interleave.cpp) selects Channel from `ingress_id`; [RITAddrMapper](../../../src/ramulator/controller/addr_mapper/impl/rit_addr_mapper.cpp) can remap Row and apply a reserved-row offset after base mapping. An original number without its mapping/routing context does not describe these final coordinates completely. |
| Translation boundary | [NoTranslation](../../../src/ramulator/translation/impl/no_translation.cpp), when invoked upstream, modifies `addr` by wrapping it to the configured address range. The proposed source is the physical/linear address presented to DRAM mapping after such translation, not necessarily an earlier frontend number. GenericDRAMSystem's send path itself does not perform virtual translation. |
| Direct PuD / pass-through | The ordered-operand constructor supplies only AddrVec operands: `addr` and `intra_channel_addr` default to -1. There is no per-operand physical address, bit offset, layout reference, or resolved internal address. Pass-through mapping supplies none of the missing information. |
| Retained commands | [Occurrence configuration](../../../src/ramulator/controller/pud_sequence.cpp) replaces `req.addr_vec` with the current operand. [Device](../../../src/ramulator/dram/device.h) receives command, AddrVec, and clock, with no shared internal target. A map keyed only by the mutable current AddrVec cannot represent all operand locations. |

**Minimum retained source information (proposed):** preserve a physical/layout
placement origin sufficient to resolve both views for each operand's region.
This may be a physical byte address with bit/region information or a resolvable
layout-region reference; a mat-row or group region need not have one scalar
byte address. When byte-address input is used, preserve the complete unrounded
address until resolution, including all low six byte-offset bits for this
baseline. Keep the origin's address-space/routing context and the
identity/configuration of the common profile.
Higher address bits may participate in channel/bank XOR/interleaving; do not
retain only a presumed fixed subset without a profile-specific sufficiency
proof. Under the retained row assumption, derive subarray/local row from the
**final** external Row after applicable transformations, not a competing raw
row decode.

A byte address alone does not identify a four-bit mat contribution. Preserve
an explicit bit-within-byte selector and requested region, or an equivalent
layout-region reference that resolves them unambiguously. A full burst
describes an ordered set of bits across mats; a compute operand describes a
mat-row region; movement describes an HFF-width group (or the accepted LC
range of such groups). No arbitrary byte/bit anchor is silently widened or
aligned to a movement group. For already-bitsliced data, layout information
must describe actual physical placement, not introduce a second functional
lane address space or require a transposer.

The source facts do not identify which omitted bits select which mats, HFFs,
or cell columns. Retaining the complete placement origin allows a replacement
profile to make that choice explicitly. Distinct offsets within one external burst
must resolve to locations within that burst's common internal footprint,
not contradictory ordinary and PuD copies of the data.

### 9.4 Accepted Gate B authority

Gate B is closed by the Accepted
[common addressing, geometry, and payload decision](../decisions/mimdram-addressing-geometry-and-payload.md).
That canonical document contains the complete generic contract, selected
profile formulas and inverse, affected-location semantics, evidence classes,
validation requirements, compatibility boundary, and live open issues.

| Accepted boundary | Resolution |
| --- | --- |
| Generic geometry | Replaceable, coordinated MIMDRAM-DDR4 profiles; no x8 constants or G/B identity in PuD operation semantics. Additional physical x4/x16 profiles are not claimed. |
| Canonical storage authority | One physical/layout-location -> CellID resolver supplies both ordinary ACT/RD/WR and PuD compute/LC-MOV/GB-MOV footprints; no independent path-specific reconstruction. |
| Initial profile | **MIMDRAM-DDR4_8Gb_x8 modeled placement profile v1**: chip-major striping, 1024 organization Columns, DQ8, 16 mats/chip context, 512 cells/mat-row, four HFFs/mat, and the retained 1024-row subdivision. These values belong only to this instance. |
| Placement convention | Chip-major is an explicit simulator convention, not vendor DQ/beat/bitline wiring. Byte-lane was considered and remains unselected. |
| Operand lifetime and scope | Paired resolved operands and origin/profile association survive execution without selecting C++ storage. Mat-scoped compute requires an explicit non-empty contiguous range; no missing-range fallback. |
| Validation | Geometry equations and bijection establish capacity/non-aliasing; implementation tests must additionally verify that ordinary and PuD paths use the shared resolver and identify the same cells. |

The former proposal and pending Gate B approval list are replaced by that
canonical authority. Sections 9.1–9.3 retain the investigation's technical
evidence and source limits; their proposal-era wording is provenance, not
an additional approval gate.

### 9.5 Accepted Gate A authority

**Gate A is Accepted, 2026-09-08**, in the canonical
[substrate and experiment boundary](../decisions/mimdram-substrate-and-movement-request-boundary.md).
That authority records the PRADA-compute/MIMDRAM-execution hybrid, required
disjoint compute overlap and conservative movement policy, width-independent
local compute costs distinct from Gate C overhead, substrate/macro separation,
four-residual/host completion, supported connectivity, and experiment limits.
It includes the user's timing, macro-scope, and overlap-validation clarifications.

Gate B remains Accepted and unchanged. Gate A accepts its conditional hybrid
compute effects without asserting circuit compatibility or adding a scalar
reduction mechanism. Gate A's overlap wording was narrowly clarified with
Gate C: same-Bank MIMD is required within one subarray; cross-subarray compute
is serialized, without implicit SALP.

### 9.6 Accepted Gate C authority

**Gate C is Accepted, 2026-09-09**, in the existing canonical
[execution/state/lifecycle decision](../decisions/mimdram-movement-execution-ownership-and-device.md)
and [timing/resource/transport decision](../decisions/mimdram-movement-timing-and-resource-model.md).
Their v2 sections are the current authority; retained legacy sections describe
the executable baseline and unchanged movement contracts.

The accepted execution authority defines range contexts, first-fit compute
allocation with E=8, engine/range release at terminal recovery, same-subarray
overlap, conservative movement/ordinary/maintenance interaction, and the
separate functional simulator. The timing authority selects per-activation
target transport (Alternative A), explicit initial setup, eight-entry per-chip
queues with labeled simulator semantics, shared C/A occupancy independent of
PRADA timing anchors, and the fine-grained-ACT bound/rounding calculation.
Recover those contracts from the canonical documents rather than the earlier
investigation's open-gate wording.

Gate B is unchanged. No code or implementation plan was created by accepting
Gate C, and executable v2 support is not claimed. Remaining physical-fidelity
limits and future implementation validation are recorded in the canonical
authorities, not new unresolved Gates A/B/C.
