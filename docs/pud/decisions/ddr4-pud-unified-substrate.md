Status: Accepted

Question

What is the canonical public DDR4 PuD execution model after completion of the
PRADA/MIMDRAM W1-W9 substrate, and how does a caller explicitly select either
the complete modeled mat range or a narrower compute range?

Decision

Use the completed W1-W9 PRADA/MIMDRAM substrate as the single canonical public
DDR4 PuD execution model. The public substrate combines compute and movement;
there is no separate public compute-only versus movement-capable PuD execution
semantics. This is a project architecture choice, not a claim that PRADA and
MIMDRAM are one source design or that their complete physical implementations
are interchangeable.

The substrate inherits different source mechanisms:

- PRADA supplies the underlying RowCopy, TRA/three-row-majority,
  5RA/five-row-majority, and NOT mechanisms and timing evidence.
- The project exposes TRA and 5RA as the `MAJ3` and `MAJ5` request types.
  `NOT_COPY` is a project request-level composition using the accepted
  PRADA-based mechanisms; it is not a separately attributed PRADA primitive.
- MIMDRAM supplies fine-grained mat organization and selection concepts,
  disjoint-range MIMD motivation, and the LC-MOV and GB-MOV mechanisms.
- `PlacementProfile` and `LocationResolver` are project abstractions. The
  project combines the source mechanisms through its accepted placement,
  range-state, allocation, conflict, timing, transport-abstraction, recovery,
  and completion contracts. The hybrid combination and its fidelity limits are
  project decisions.

Every compute operand must be constructed against an explicitly selected,
supported `PlacementProfile`/`LocationResolver`. The caller must explicitly
provide exactly one of these target forms:

```text
FULL_MAT

MatRange{first, last}
```

`FULL_MAT` is a strongly typed user-facing construction token/tag. It is not an
omitted argument, `std::nullopt`, or a negative or magic numeric range. The
canonical construction path is:

```text
LocationResolver
    -> compute_footprint(row, FULL_MAT or MatRange{first, last})
    -> ResolvedRegion
    -> pair(...)
    -> PairedOperand
    -> Request
```

For an explicit `MatRange`, validate and resolve that range. For `FULL_MAT`,
resolve through the selected profile during `compute_footprint` construction:

```text
FULL_MAT
    -> MatRange{0, resolver.logical_mats() - 1}
    -> normal ResolvedRegion / RequestLocations
```

Store only the resulting explicit range in the immutable resolved
request-location authority shared by every operand and occurrence. Do not add a
second Request constructor merely to represent `FULL_MAT`; later implementation
inspection may add one only if the existing resolver-to-pair-to-Request path is
shown to be insufficient.

Missing or omitted compute target selection is invalid at the public
construction boundary. After construction, neither `FULL_MAT` nor any
optional/missing/full sentinel is representable execution state. Every compute
Request and occurrence carries an explicit resolved `MatRange`; validation,
allocation, sequencing, Device dispatch, local timing, conflict protection,
terminal range close, recovery, completion, and accounting all use the W1-W9
range-aware path. Full-mat execution is only the resolved full-range case of
that path. It is not a separate Bank-wide execution mode.

Bare `AddrVec_t` operands alone do not contain a placement origin, profile
association, or resolved mat range. The existing bare ordered-operand Request
constructor therefore cannot by itself construct a canonical compute request.
A public convenience API may accept address vectors only if it also has the
resolver/profile context and explicit `FULL_MAT` or `MatRange` selection needed
to produce the same resolved request-location authority during construction.
Controller or Device ingress must not infer a full range from missing internal
metadata, silently fall back to Bank-wide compute, or retain missing range as a
sentinel.

Movement is part of the same canonical public DDR4 PuD substrate and uses the
same placement and request-location authority; this does not create a separate
movement execution model. LC-MOV requires its explicit source and destination
groups over an explicit common mat range. GB-MOV requires explicit source and
destination singleton mat/group endpoints satisfying the profile topology.
Omitted movement endpoints or ranges are invalid. `FULL_MAT` has no implicit
GB-MOV interpretation and must not be used to invent one.

The old Bank-wide PRADA compute path and the W1-W9 range-aware compute path are
not two supported runtime models after consolidation. Runtime or configuration
selection may choose a supported placement profile or compute-engine capacity,
but must not select legacy versus range-aware compute semantics. Absence of an
explicitly selected supported placement profile makes canonical PuD execution
unavailable; it must never select Bank-wide compute. Movement uses the same
protected invocation machinery with the
[Accepted physical-mat footprint scope](mimdram-movement-execution-ownership-and-device.md).
It acquires at first ACT, consumes no compute engine, and protects only its
footprint through recovery. There is no Bank-wide movement fallback.

Historical `v2` terminology identifies the development and verification effort
that produced the canonical substrate. It is non-normative in the final user
model. Names such as `DDR4_PuD`, `DDR4_PuD_Movement`, `ddr4_pud.py`, request and
command identifiers, generated standard definitions, timing tables, and shared
helpers may remain when they are useful implementation structure. Their names
do not create separate legacy/v2 or compute-only/movement-capable public
semantics. Implementation must expose one public configuration for the unified
compute-and-movement substrate while preserving reusable internal layering as
appropriate.

This decision does not add DRAM value simulation, arithmetic macros, reduction
lowering, primitive-trace replay, a compiler, or a new movement topology. The
completed W1-W9 plan remains implementation history rather than the definition
of the final user model.

Rationale

The completed substrate already provides one canonical placement authority,
resolved request-location lifetime, explicit range contexts, first-fit engine
allocation, range-local timing and recovery, physical-mat movement interaction,
and exact-once completion. Keeping an alternate no-range Bank-wide compute path
would preserve two meanings for the same public compute primitives, bypass the
canonical location authority, and make configuration rather than request
semantics determine affected resources.

Requiring `FULL_MAT` makes full-range intent explicit without leaking a special
case into execution. Resolving the tag immediately gives full-range and
subrange requests identical validation, scheduling, state, timing, and
completion rules. Keeping movement endpoints explicit avoids inventing a
full-range interpretation for operations whose semantics depend on ordered
source/destination groups and topology.

Preserving reusable PRADA and movement definitions avoids unnecessary
reimplementation and keeps standard DDR4 isolated. The consolidation removes
an execution distinction, not implementation provenance or every identifier
created while the substrate was developed.

Evidence

- [Completed W1-W9 implementation record](../plans/mimdram-pud-substrate-v2-implementation-plan.md)
  records the implemented resolver, paired-request retention, range-local
  Device state/timing, protected recovery lifetime, conflict rules, resolved
  target consumption, engine allocation, public ingress, benchmarks, and final
  integration validation.
- [Addressing, geometry, and payload](mimdram-addressing-geometry-and-payload.md)
  defines the replaceable placement profile, canonical CellID authority,
  explicit compute ranges, and movement endpoint footprints.
- [Substrate and movement boundary](mimdram-substrate-and-movement-request-boundary.md),
  [execution/lifecycle](mimdram-movement-execution-ownership-and-device.md),
  [timing/resources](mimdram-movement-timing-and-resource-model.md), and
  [target transport](mimdram-mat-target-transport-abstraction.md) define the
  accepted hybrid, range concurrency, footprint-local movement, local/shared
  timing, recovery, and resolved-target abstraction retained here.
- [PRADA primitives](../references/pud-primitives.md),
  [DDR4 PuD timing](../references/ddr4-pud-timing-reference.md), and
  [MIMDRAM movement](../references/mimdram-inter-column-data-movement.md)
  distinguish the inherited source mechanisms from the project's hybrid and
  execution choices.
- Current source retains the bare ordered-`AddrVec_t` constructor for internal
  compatibility, but public compute ingress requires the resolver/paired-operand
  constructor and canonical resolved locations.
  `LocationResolver::compute_footprint` resolves `FULL_MAT` or an explicit
  `MatRange` before `pair` and Request construction. The configured profile
  installs that resolver, GenericDDR uses the protected range-aware path, and
  both public benchmarks invoke the unified substrate without a mode selector.

Open issues

- No execution-semantics or implementation-packaging issue remains for the
  canonical public path. Reusable `DDR4_PuD` and `DDR4_PuD_Movement`
  definitions remain implementation structure, not separate public models.
- Additional placement profiles, physical transport fidelity, functional value
  simulation, and higher-level arithmetic or reduction execution require
  separate future decisions and implementation.
