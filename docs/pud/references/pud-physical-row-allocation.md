# Physical-row allocation for fixed PuD primitive traces

This reference investigates storage allocation for the symbolic traces emitted
by `tools/pud_operation_generator`. It records current behavior, source-backed
primitive facts, established allocation results, and derivations. It does not
select an allocator contract or change the generator, interpreter, generated
sequence, or simulator.

Historical scope: the code observations below describe the pre-lowering,
widened-output generator investigated for the original allocation decision.
In particular, its INT8 9/16-output table is historical, not the current
operation interface. The subsequent fixed-width INT8 contract and current
counts are documented in the [generator README](../../../tools/pud_operation_generator/README.md)
and [accepted lowering decision](../decisions/pud-operation-physical-lowering.md).
The physical-source facts below are unchanged by that project interface choice.

The labels used below have these meanings:

- **Source fact** — stated by the original cited PRADA paper or by the
  checked-in PRADA-derived references.
- **Current-code fact** — directly implemented by the current generator,
  interpreter, manifest writer, tests, or canonical PuD request path.
- **General algorithmic fact** — an established compiler or storage-allocation
  result independent of this project.
- **Derived implication** — a consequence of the cited facts under explicitly
  stated assumptions.
- **Undecided project question** — a contract or policy choice not fixed here.

## 1. Current generator facts

### 1.1 Row creation, definition, and observation

- **Current-code fact.** `Builder` starts with the 16 input names `A0..A7` and
  `B0..B7`, plus the symbolic names `CONST_ZERO` and `CONST_ONE`. A profile's
  `constants` dictionary determines which constants are actually declared and
  initialized. Inputs and declared constants are defined at program entry.
  `CONST_ONE` is not used or declared by profiles that need only zero.

- **Current-code fact.** `new_row()` creates a fresh, monotonically numbered
  symbolic name `tNNNN` and records the name in `Builder.rows`; it does not give
  the row a value. A work row becomes value-defined when it is first written by
  a primitive. In all eight current builders, every work row is first written
  as a fresh destination of `RowCopy` or `NOT_COPY`.

- **Current-code fact.** An output name `R<n>` is value-defined by the
  `RowCopy(source, R<n>)` emitted by `Builder.export()`. The method records all
  output names in LSB-first order, emits one single-destination copy per bit,
  and appends each output name to `Builder.rows`. All current builders call
  `export()` once, at the end of the arithmetic trace.

- **Current-code fact.** A symbolic row is not an SSA value. `NOT` writes its
  operand in place; `NOT_COPY` writes its source in place as well as its
  destinations; and `TRA`/`5RA` write every participant. A typical temporary is
  therefore first defined by a copy and redefined by a destructive primitive.
  An audit of the eight current builders finds that every emitted work row is
  written more than once, whereas every `R<n>` is written once.

- **Current-code fact.** `validate_structure()` maintains a monotonic `defined`
  set. It rejects reads before a first definition and writes to inputs or
  constants, but it does not reject later writes to an already-defined work or
  output name. It also does not enforce the builder's stronger convention that
  copy destinations are fresh. Thus freshness is a fact about the eight
  current builders, not a general property of every trace accepted by the
  parser and structural validator.

- **Current-code fact.** `execute()` keeps a dictionary entry for every
  symbolic name and never deallocates it. The exhaustive tests observe final
  outputs and, for selected profiles, diagnostic taps or a discarded carry;
  serialized replay also compares the complete final symbolic-row dictionary.
  This interpreter behavior is not itself a physical lifetime contract.

- **Undecided project question.** Must a physical execution preserve the final
  observability of every symbolic row, every manifest diagnostic tap, and every
  discarded carry, or only the protected inputs/constants and bound outputs?
  Requiring all symbolic entries at exit would intentionally prevent most
  storage reuse unless the validator records virtual snapshots separately.

### 1.2 Read/write effects in the symbolic interpreter

| Primitive | Classification | Reads the old value of | Writes | Old destination value needed? |
| --- | --- | --- | --- | --- |
| `RowCopy(src, dst...)` | **Current-code fact** | `src`, snapshotted before any write | every `dst`; `src` is unchanged | no |
| `NOT(row)` | **Current-code fact** | `row` | the same `row` with its bits inverted | yes |
| `NOT_COPY(src, dst...)` | **Current-code fact** | `src`, snapshotted before any write | `src` and every `dst` with the inverted snapshot | no for destinations |
| `TRA(a,b,c)` | **Current-code fact** | all three rows, snapshotted before any write | all three with the majority of the old values | yes for every participant |
| `5RA(a,b,c,d,e)` | **Current-code fact** | all five rows, snapshotted before any write | all five with the majority of the old values | yes for every participant |

- **Current-code fact.** `validate_structure()` requires every row role within
  one primitive to have a distinct symbolic name. This includes the source and
  all destinations of `RowCopy` and `NOT_COPY`, and all majority participants.

- **Current-code fact.** The generator-side trace format and interpreter allow
  multiple `NOT_COPY` destinations, but all current builders emit one. The
  canonical Ramulator request interface currently accepts exactly one
  `NOT_COPY` destination. Physical allocation of the eight existing profiles
  therefore does not require a new multi-destination request contract.

### 1.3 Gaps, redefinitions, and resurrection

- **Current-code fact.** Current work rows can have arbitrarily many primitive
  positions between accesses. Their values remain stored in the symbolic
  interpreter during such gaps. The generated traces contain many such gaps.

- **Derived implication.** A gap between two accesses is not a dead interval
  when the later access reads the value left by the earlier access. A physical
  allocator must retain the value throughout the gap.

- **Current-code fact.** In the eight current builders, a work row's first
  write is fresh and every later write to it also reads its old value in the
  same primitive. Consequently, a current generated work-row identity does not
  die and later reappear through a write that ignores its old value.

- **Current-code fact.** The broader structural validator would accept a
  `RowCopy` destination or `NOT_COPY` destination that overwrites a previously
  defined, nonprotected row. Such a trace could kill one value of a symbolic
  name and later define an unrelated value under the same name.

- **Derived implication.** Supporting that broader language with live-range
  splitting would require versioning definitions or permitting one symbolic
  identity to change physical binding. Neither follows from the current
  generated traces. Under identity-preserving allocation, the conservative
  lifetime of such a reused name is still the convex interval from its first
  requirement through its last requirement.

### 1.4 Inputs, constants, work rows, outputs, and manifests

- **Current-code fact.** `validate_structure()` designates inputs and declared
  constants as `protected`, rejects every primitive write to them, and starts
  them in the `defined` set. `execute()` defaults its protected set to all
  initially supplied rows and checks at exit that their values equal their
  entry values. The profile validation supplies exactly the inputs and declared
  constants as initial rows. The current generator contract therefore
  deliberately preserves inputs and constants for the whole symbolic replay.

- **Current-code fact.** Builder helpers preserve their arguments by copying
  them before destructive majority or NOT work. Work rows are not protected.
  Output rows are not in the protected set, but current exports are terminal so
  no later primitive overwrites them.

- **Current-code fact.** A row manifest partitions the row names actually used
  in the trace into inputs, declared constants, `outputs_lsb_first`, and
  `work_rows`. `work_rows` is a set difference sorted by name, not a liveness
  order. Its size is the number of distinct logical work names, not a physical
  row requirement or peak-live count.

| Profile | Classification | Logical work names | Output names / terminal output copies |
| --- | --- | ---: | ---: |
| `uint8-add` | **Current-code fact** | 42 | 9 |
| `uint8-mul` | **Current-code fact** | 584 | 16 |
| `int8-add` | **Current-code fact** | 47 | 9 |
| `int8-mul` | **Current-code fact** | 591 | 16 |
| `fp8-e5m2-add` | **Current-code fact** | 813 | 8 |
| `fp8-e5m2-mul` | **Current-code fact** | 275 | 8 |
| `fp8-e4m3-add` | **Current-code fact** | 1,028 | 8 |
| `fp8-e4m3-mul` | **Current-code fact** | 281 | 8 |

- **Current-code fact.** Manifest `arithmetic_core_primitives` subtracts one
  terminal output-copy primitive per output bit, and
  `physical_allocation_and_timing` explicitly says physical allocation is not
  implemented. The tests validate primitive counts, symbolic structure,
  input/constant preservation, arithmetic results, and serialized symbolic
  replay; they do not establish a minimum physical-row count.

- **Current-code fact.** The canonical simulator path requires each compute
  request to carry resolver-produced locations for an explicit common
  `MatRange` (or an explicitly resolved `FULL_MAT`) in one Bank/subarray
  context. The accepted v1 profile has 1,024 local rows per subarray. Current
  request validation explicitly rejects equal local rows among `MAJ3` or
  `MAJ5` operands. These location facts constrain a future allocator's legal
  pool but do not choose which rows are reserved, preassigned, or reusable.

Relevant current authorities are the
[unified substrate decision](../decisions/ddr4-pud-unified-substrate.md), the
[addressing, geometry, and payload decision](../decisions/mimdram-addressing-geometry-and-payload.md),
and the current implementation in
[`core.py`](../../../tools/pud_operation_generator/core.py),
[`artifacts.py`](../../../tools/pud_operation_generator/artifacts.py), and
[`validation.py`](../../../tools/pud_operation_generator/validation.py).

## 2. Primitive-specific lifetime/interference facts

### 2.1 Command-time distinctness

- **Source fact.** PRADA RowCopy first senses the source row, then enables each
  destination wordline before final precharge:
  `A_S*(src) -> A(dst0) -> ... -> P`. PRADA's NOT-and-Copy sequence similarly
  performs `A_S*(src) -> N -> A(dst) -> P`. See
  [PuD primitives](pud-primitives.md) and the
  [timing reference](ddr4-pud-timing-reference.md).

- **Derived implication.** The PRADA sequences require the source and each
  destination to denote distinct physical rows during RowCopy and
  NOT-and-Copy. Reusing the already enabled source wordline as its destination
  does not perform the described second-row activation or create a separate
  copy. Multiple destinations likewise require distinct destination rows.

- **Current-code fact.** The symbolic validator already requires distinct
  roles for these primitives. The current canonical C++ placement validator
  explicitly checks physical-row distinctness for majority operands, but does
  not make the analogous same-local-row rejection for `RowCopy` or
  `NOT_COPY`. Functional equality alone would not expose this physical
  illegality.

- **Source fact.** PRADA's TRA and 5RA sequences activate three and five
  participating rows respectively, allow their cells/bitlines to charge
  share, and perform final sensing only after all participants have joined.

- **Current-code fact.** The accepted canonical compute effect requires
  distinct physical-row operands for `MAJ3` and `MAJ5`; after the operation,
  every participating row contains the majority of the pre-operation operand
  values.

- **Derived implication.** All three TRA participants, and all five 5RA
  participants, form pairwise interference cliques at that command. They must
  stay physically distinct even though their values are equal afterward.
  Repeating one physical wordline would not supply the described number of
  independently stored charge-sharing operands.

### 2.2 Lifetime endpoints

- **Derived implication.** Model a primitive position as an indivisible
  command point for allocation. Every row read or written by that primitive is
  occupied at that point. A destination first defined there starts its lifetime
  at that point; an operand with no later need ends its lifetime only after the
  point.

- **Derived implication.** A `RowCopy` or `NOT_COPY` destination cannot reuse
  the physical row of its source, another destination, or any other operand in
  the same primitive even when that operand's last symbolic use is the current
  primitive. This is the principal difference from a register instruction set
  that permits a dead source register to become the destination register.

- **Derived implication.** A physical row whose last required command is
  primitive `i` may be reused by a row first required by primitive `i+1` or
  later, subject to protection, placement, and recovery constraints. It may
  also be used by a destination at `i` if it is not itself any role in `i` and
  its prior lifetime ended before `i`.

- **Derived implication.** `NOT` adds no edge between different identities: it
  transforms one identity in place. TRA/5RA also introduce no new destination
  identities, but their read-before-write behavior keeps every participant
  occupied at the command point. `NOT_COPY` keeps its source identity occupied
  across the in-place inversion and begins each destination identity at the
  same command point.

### 2.3 Four different transformations

- **General algorithmic fact.** *Ordinary lifetime reuse* assigns the same
  storage unit to different identities whose required lifetimes do not
  overlap. It neither merges values nor changes instructions.

- **General algorithmic fact.** *Copy coalescing* merges the identities on the
  two sides of a copy and removes the copy when the merged live range remains
  legal. It is not the same transformation as assigning one unit to two
  nonoverlapping lifetimes.

- **Derived implication.** An internal PuD RowCopy cannot remain in the trace
  with aliased source and destination. Coalescing it requires deleting or
  replacing that primitive and proving all subsequent destructive uses remain
  correct. Terminal output-copy removal is a narrower case analyzed in
  Section 5.

- **General algorithmic fact.** *Value-equivalence coalescing* redirects two
  identities to one storage value because analysis proves their contents are
  equal. Equality alone does not establish that later writes, simultaneous
  operand roles, or separately observable identities may be merged.

- **Derived implication.** RowCopy, `NOT_COPY`, TRA, and 5RA all create equal
  values in multiple rows, but those equalities do not permit identity-level
  aliasing under the fixed symbolic semantics. A later destructive operation
  can make the identities diverge, and a later primitive may require them as
  distinct physical participants.

- **General algorithmic fact.** *Primitive reordering or recomputation*
  changes when values are produced, retained, or regenerated. It changes live
  ranges by changing the program rather than by allocating the fixed program.

## 3. Established allocation algorithms and applicability

### 3.1 Liveness, intervals, and interference

- **General algorithmic fact.** Liveness asks whether the current stored value
  will be read in the future before an overwriting definition makes that value
  irrelevant. An interference graph connects identities that must occupy
  different storage simultaneously. General register allocation commonly
  colors such a graph; graph coloring is not generally an interval problem.

- **Derived implication.** For the current generated traces under one fixed
  physical binding per symbolic identity, define an identity's start as entry
  for an input/constant or its first defining command otherwise. Define its end
  as its last required command, extended to program exit if the contract
  protects or externally observes it. Its physical row must hold the identity
  continuously between those endpoints, including gaps between accesses.

- **Derived implication.** Each such identity therefore has one closed
  interval in fixed instruction order. Two identities interfere exactly when
  their intervals overlap, provided all same-primitive roles are included at
  the primitive point. The resulting graph is an interval graph. Destructive
  redefinitions do not make it non-interval because the identity and physical
  binding persist across the read-modify-write operation.

- **General algorithmic fact.** Interval graphs are perfect: their chromatic
  number equals their largest clique. For homogeneous, unit-capacity storage
  with no precoloring or eligibility restrictions, the minimum number of
  storage units is the maximum number of simultaneously live intervals.
  Processing intervals by start position and reusing a unit whose prior
  interval has already ended obtains this optimum. With closed command-point
  endpoints, reuse requires `old_end < new_start`, not equality.

- **Derived implication.** Ordinary interval coloring is sufficient for an
  optimal identity-preserving, fixed-order allocation only when physical rows
  are interchangeable within the legal placement pool and there are no extra
  fixed-address, row-class, reservation, or observability constraints. The
  peak-live count is then both a lower bound and an achievable allocation.

### 3.2 Linear scan, registers, storage, and constraints

- **General algorithmic fact.** Linear-scan register allocation maintains the
  intervals active at the current program point and reuses expired registers.
  In the unlimited homogeneous-unit problem above, this is the standard
  optimal interval-partitioning algorithm. Linear-scan spill choices with a
  fixed register limit solve a different problem and are not automatically
  globally optimal.

- **General algorithmic fact.** Register allocation supplies the useful
  notions of live ranges, interference, precoloring, copy coalescing, and
  spilling/rematerialization. A DRAM row is nevertheless not a CPU register:
  PuD primitives impose multi-row physical participation and destructive
  effects, and obtaining a displaced value would require an explicit DRAM
  operation rather than a free compiler rename.

- **General algorithmic fact.** Classical storage allocation also assigns
  memory to objects over time. Because every object here occupies exactly one
  row, variable-sized dynamic-storage packing results are unnecessary for the
  basic model; unit-size interval allocation is the closer problem.

- **General algorithmic fact.** Precoloring fixes an identity to a particular
  storage unit. Per-identity eligibility lists or distinct row classes further
  constrain colors. Ordinary unconstrained interval coloring does not by
  itself prove feasibility or optimality for these constrained variants.

- **Derived implication.** A designated output physical row is a preassigned
  color, not necessarily a row reserved from program entry. If an output
  identity or its coalesced final-source identity is precolored to that row,
  an earlier temporary whose interval ends before the precolored identity
  begins may use the same physical row. The ordinary command-point and
  primitive-distinctness rules still apply at the lifetime boundary.

- **Derived implication.** Fixed input addresses, dedicated constant rows,
  fixed result addresses, reserved compute rows, differing per-primitive row
  eligibility, or a requirement to preserve taps at exit would turn the
  simple interval problem into a constrained allocation problem. These
  constraints must be represented explicitly rather than hidden in a live
  interval heuristic.

### 3.3 When interval coloring would cease to describe the whole problem

- **Derived implication.** Non-interval structure appears if one symbolic
  identity is allowed to have disconnected value segments but is still forced
  to use one common physical color, if value-equivalent identities are merged
  across disconnected segments, or if allocation is coupled to instruction
  scheduling/recomputation. Extra physical eligibility and precoloring may
  also make interval coloring insufficient even though the temporal
  interference subgraph remains an interval graph.

- **Derived implication.** Primitive distinctness does not by itself create a
  non-interval graph for the current traces. Treating every role as live at the
  command point places all required pairwise edges at a common point. An
  allocator that instead uses conventional half-open definition/use endpoints
  must add the same-command distinctness edges explicitly.

- **General algorithmic fact.** Standard references for these results include
  Chaitin et al., “Register Allocation via Coloring” (1981); Poletto and Sarkar,
  “Linear Scan Register Allocation” (1999); George and Appel, “Iterated
  Register Coalescing” (1996); and Fulkerson and Gross, “Incidence Matrices and
  Interval Graphs” (1965). These results establish the generic algorithms, not
  this project's physical-row policy.

## 4. Minimum-row problem variants

| Variant | Classification | Meaning of “minimum physical rows” | Relative complexity | Executes the original primitive sequence unchanged? |
| --- | --- | --- | --- | --- |
| A. Identity-preserving fixed order | **Derived implication** | One fixed physical row per live symbolic identity; reuse only after that identity's required interval ends; keep every primitive and operand identity. If outputs have designated physical rows, precolor each retained `R<n>` identity to its designated row. | Optimal interval coloring only in the homogeneous unconstrained case; designated outputs, other precoloring, protection, or row eligibility make it constrained. | Yes: same primitives, order, and distinct symbolic roles. |
| B. A plus terminal output-copy coalescing | **Derived implication** | Remove `RowCopy(final_source, R<n>)` only by precoloring `final_source` to `R<n>`'s designated physical row for the final source's entire interval, and extend that interval through the required output lifetime. Earlier nonoverlapping temporaries may use the designated row. | A local semantic proof plus a constrained/precolored interval-allocation problem; unconstrained interval partitioning and maximum interval depth alone do not establish the optimum. | No in the literal sense because terminal RowCopy primitives are deleted. The arithmetic-core primitive order can remain unchanged. |
| C. Value-equivalence aliasing | **Derived implication** | After RowCopy, `NOT_COPY`, TRA, or 5RA establishes equal contents, redirect multiple symbolic identities to one physical value where all future destructive and distinct-role uses permit it. | Requires value/version analysis, future distinctness checks, divergence handling, and possibly copies to split aliases again. | Not in general. Some cases may retain opcode order, but symbolic identity and physical operand bindings no longer implement the original identity semantics. |
| D. Global scheduling/recomputation | **Derived implication** | Change primitive order, retain different intermediates, recompute values, or select a different Boolean microprogram to reduce peak storage. | A global code-generation/scheduling problem coupled to destructive legality and cost. | No. It intentionally changes the original primitive sequence. |

- **Undecided project question.** Which variant defines the allocator's claim,
  and which row classes count in its reported minimum? This reference does not
  select among A-D. Ordinary lifetime reuse and the narrow terminal-output
  transformation are the only variants identified as plausible initial scope
  by the research request, not accepted policy.

## 5. Output-copy coalescing analysis

### 5.1 Exact transformation

- **Current-code fact.** Today each output bit ends with this symbolic action:

  ```text
  RowCopy(symbolic_final_source, Rn)
  ```

  `Rn` becomes a distinct symbolic row containing the source value; the source
  remains unchanged.

- **Derived implication.** Let `P(Rn)` be the designated physical row for
  output `Rn`. With the terminal copy retained, the physical constraints are:

  ```text
  physical(Rn) = P(Rn)
  physical(symbolic_final_source) != P(Rn) at the RowCopy command
  ```

  `Rn` begins occupying `P(Rn)` at the copy command and remains there through
  its required output lifetime. A temporary whose lifetime ends before that
  command may previously use `P(Rn)`; designation does not by itself reserve
  the row from program entry.

- **Derived implication.** Eliminating the terminal copy changes the
  allocation constraint to:

  ```yaml
  physical(symbolic_final_source): P(Rn)
  ```

  The RowCopy is removed, and `symbolic_final_source` is precolored to the
  designated output row for its entire live interval. The allocator does not
  choose an arbitrary physical row and then bind `Rn` to it. An earlier
  temporary may use `P(Rn)` only if its interval ends before the final source
  becomes live. While the final source is live, the row may evolve only through
  primitives that define or update that identity; after its final
  result-producing primitive, the result must remain valid there through the
  required output lifetime.

- **Current-code fact.** In every current profile, every output-copy source is
  a work row, the sources for different output bits are pairwise distinct, and
  export is the final trace stage. No arithmetic primitive follows the export
  copies.

### 5.2 Correctness conditions

- **Derived implication.** The transformation preserves the arithmetic result
  if all of the following hold:

  1. The copy primitive is deleted; source and destination are not physically
     aliased while pretending to execute RowCopy.
  2. The final source already contains exactly the output bit value at the
     point where the deleted copy would have read it.
  3. The final source is precolored to `P(Rn)` from the beginning of its live
     interval, and all primitives defining or using it are legal with that
     fixed assignment.
  4. Any earlier temporary use of `P(Rn)` ends before the final source becomes
     live, no other identity uses it during the final source's interval, and
     after the final result-producing primitive its value remains unmodified
     through the required output lifetime.
  5. No contract requires both the final source identity and `Rn` to be
     independently writable or independently observable after coalescing.
  6. The designated rows for distinct result bits satisfy the output placement
     contract, and precoloring their current pairwise-distinct final sources
     creates no physical conflict.
  7. Input/constant protection and any diagnostic-tap observability remain
     satisfied if a future output source belongs to one of those classes.
  8. Removing the copy's latency, statistics, trace event, and physical side
     effect is within the selected observable contract; arithmetic equality
     alone does not decide those nonfunctional observables.

- **Derived implication.** Under those conditions, removal does not change the
  value delivered for any current output bit and removes the distinct `R<n>`
  identity and its copy command. The designated physical row still counts as a
  used row, but it may hold earlier nonoverlapping temporary identities. The
  final source occupies it from that identity's first live point through the
  output-consumption boundary.

- **Derived implication.** This transformation is safe only as precoloring the
  final source to the designated result row, not as choosing an arbitrary
  source row or retaining an aliased RowCopy. It therefore preserves the
  arithmetic-core sequence but not the literal full primitive sequence
  currently serialized.

- **Derived implication.** Because the final source is forced to a designated
  color, this formulation is a constrained/precolored interval-allocation
  problem. Its optimum need not equal the unconstrained maximum interval
  depth, even though every temporal lifetime remains an interval.

- **Undecided project question.** Does the project adopt designated-output
  precoloring and permit deletion of the output copies? Are those copies
  architecturally or timing observable? This reference analyzes the
  formulation without accepting it.

## 6. PRADA source facts

This section uses the original cited PRADA paper, especially its Introduction,
Section 4.2, and Conclusion, together with the checked-in PRADA-derived
[primitive](pud-primitives.md) and
[timing](ddr4-pud-timing-reference.md) references and the provenance statements
in the generator [README](../../../tools/pud_operation_generator/README.md).

- **Source fact.** One-destination RowCopy uses a sensed source row and one
  destination row. Multi-destination RowCopy adds one destination activation
  per copied row. The source is preserved by the described copy operation.

- **Source fact.** Temporal NOT acts in place on a value already available in
  a temporary source row. The timing reference states that the ordinary-NOT
  comparison includes a RowCopy to prepare the NOT source, whereas temporal
  NOT removes that preparation copy.

- **Source fact.** PRADA's NOT-and-Copy example in its 2-bit ADD sequence
  inverts the source and then copies the inverted value to a destination before
  precharge. The checked-in source summary reports the command sequence but no
  minimum reusable-row allocation for the complete ADD.

- **Source fact.** TRA requires three participating activated rows and 5RA
  requires five. PRADA's cited AND example prepares three writable majority
  participants by copying zero to `C`, `A` to `X`, and `B` to `Y`, then invokes
  `TRA(X,Y,C)`. This is a source-supported operation sequence using three
  writable participant rows; the checked-in material does not claim that it is
  a globally minimum scratch-row allocation.

- **Source fact.** The generator README attributes its UINT8 addition
  structure to PRADA Section 5.2/Table 2, its multiplication structure to
  Section 5.4/Table 3, and its E5M2 dataflows to Figures 6 and 7. The generator
  retains or adapts those structures and adds project derivations, including
  eight-bit multiplication compressor ordering, INT8 microprograms, and E4M3
  width adaptations.

- **Current-code fact.** The manifest's `work_row_names` and primitive counts
  are counts for this generator's symbolic traces. They are not PRADA-reported
  temporary-row counts and are not physical minima.

- **Source fact.** PRADA states that Sequential Row Activation removes the need
  for designated computation rows and custom row decoders, and that PRADA can
  utilize any row for computation. This arbitrary-row compute eligibility is
  an explicit architectural property in the paper's Introduction, Section
  4.2, and Conclusion.

- **Source fact.** Neither the original PRADA paper nor the checked-in derived
  references provide a physical-row allocation algorithm or minimum
  temporary-row counts for the complete arithmetic operations represented by
  the eight profiles. They do not specify how an allocator should preserve,
  reserve, or reuse inputs, constants, intermediates, and results across a
  generated arithmetic trace.

- **Derived implication.** A future allocator may rely on PRADA's absence of
  designated compute rows and its any-row compute capability as source-backed
  eligibility. That fact does not determine this project's legal allocation
  pool, protection and precoloring contract, placement restrictions, or a
  scratch-row minimum for any generated profile.

## 7. Derived validation requirements

- **Derived implication.** A future physical-row validator needs a precise
  per-command read/write model and must replay old operands from a snapshot
  before applying `NOT_COPY`, TRA, or 5RA writes.

- **Derived implication.** For every primitive, it must reject illegal physical
  aliasing among roles required to be distinct: source versus destination and
  destination versus destination for RowCopy/`NOT_COPY`, and every pair of
  TRA/5RA participants. This legality check is separate from value replay.

- **Derived implication.** It must prove that no two simultaneously required
  identity intervals share a physical row and that reuse occurs only after the
  earlier interval's final command point. If the allocator claims the
  unconstrained identity-preserving minimum, the validator can independently
  compute maximum interval depth and require the used-row count to equal that
  lower bound.

- **Derived implication.** It must check all physical placement constraints:
  valid row bounds, common canonical Bank/subarray and selected `MatRange`, any
  declared reserved or precolored rows, and primitive-specific eligibility.
  It must not infer such eligibility from the symbolic manifest.

- **Derived implication.** Physical replay must produce the same bound final
  result as symbolic replay for the full validation input domain. If the chosen
  contract also protects inputs, constants, taps, discarded carries, or other
  symbolic state, compare those values at their specified observation points.

- **Derived implication.** If terminal output copies are removed, validation
  must verify that each final source is assigned to its output's designated
  physical row for its entire interval, that earlier users of that row are
  nonoverlapping, that the source value and extended output lifetime are
  correct, and that no required copy event or separately observable `R<n>`
  identity was removed.

- **Derived implication.** The reported row count must define its accounting
  boundary: work rows only, all simultaneously occupied rows, protected and
  precolored rows, result rows, and any physically reserved but unused rows.
  The validator must count according to that same definition and distinguish
  “uses no more than K rows” from a proved minimum of K.

- **Derived implication.** A designated output row is counted once as a
  physical row used by the allocation; sharing it with earlier nonoverlapping
  temporaries does not add rows. Conversely, precoloring a final source to that
  row may prevent an otherwise optimal unconstrained coloring, so an
  unconstrained peak-live bound does not by itself prove the claimed
  designated-output minimum.

- **Derived implication.** For a constrained allocation, a peak-live interval
  bound may remain a lower bound without proving attainability. A minimum claim
  then needs either an independently checkable optimality argument for the
  selected constraint class or an exhaustive/solver certificate appropriate
  to that class.

## 8. Questions requiring a project decision

1. **Undecided project question.** Is the first allocator's objective variant
   A, designated-output variant B, or another precisely delimited variant? In
   particular, does the project adopt designated output rows and allow their
   terminal copies to be deleted even though that changes the literal trace?

2. **Undecided project question.** Which state is observable after execution:
   outputs only; outputs plus preserved inputs/constants; manifest taps and
   discarded carries; or every symbolic row retained by `execute()`?

3. **Undecided project question.** May input rows be returned to the allocation
   pool after their final use, or must the current whole-program preservation
   check remain the physical contract?

4. **Undecided project question.** Must `CONST_ZERO` and `CONST_ONE` remain
   initialized across one invocation or multiple invocations, or may their
   physical rows be reused after their final use and reinitialized when needed?

5. **Undecided project question.** What precoloring policy applies to inputs
   and constants? Under the designated-output formulation, does the claimed
   minimum count every designated output row once while allowing its earlier
   nonoverlapping temporary uses, and how are genuinely reserved-but-unused
   rows reported?

6. **Undecided project question.** Given PRADA's source-backed any-row compute
   capability, which otherwise legal rows in the selected modeled
   Bank/subarray and `MatRange` belong to this project's allocation pool after
   excluding any protected, precolored, externally owned, or reserved rows?

7. **Undecided project question.** Should the physical validator add explicit
   same-row rejection for RowCopy and `NOT_COPY`, matching their physical
   activation sequences and the generator's distinct-role rule?

8. **Undecided project question.** Is allocation performed independently for
   each selected `MatRange`, with one local-row number representing the same
   symbolic bit-slice across all selected mats, and what pool is available
   within the 1,024-row modeled subarray?

9. **Undecided project question.** Is value-equivalence aliasing categorically
   out of the initial contract, and if so should allocator metadata explicitly
   state that only lifetime reuse (plus any separately accepted terminal-output
   precoloring) was used?

10. **Undecided project question.** What result lifetime ends the allocation:
    primitive completion, request callback, caller consumption, or a later
    explicit release? This boundary determines how long each precolored final
    source must retain its designated output physical row.
