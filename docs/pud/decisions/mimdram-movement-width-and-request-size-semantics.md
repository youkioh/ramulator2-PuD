Status: Accepted

Question

How should the initial LC-MOV and GB-MOV substrate represent architectural
movement width, and what should `Request::size_bytes` mean for those requests?

Decision

Treat architectural movement width, generic request byte size, and movement
statistics width as distinct concepts.

Represent the evaluated MIMDRAM organization's HFF count as an explicit,
configurable combined-standard hardware/organization parameter:

```text
hffs_per_mat = 4
```

This value means that the evaluated organization has four one-bit HFFs per
mat. It is not a DDR4 property, a universal MIMDRAM constant, request metadata,
or a Mat count in the Ramulator hierarchy. A future supported organization may
use a different value when justified by its architecture and reference
material. The exact configuration-tree path, parser representation, and C++
storage type are implementation-plan details.

Do not store a separate `movement_size_bits` field in `Request` initially.
Derive the exact architectural payload width from authoritative movement
request geometry and the configured `hffs_per_mat` value.

For an LC-MOV with inclusive logical mat range `[mat_begin, mat_end]`:

```text
selected_mat_count = mat_end - mat_begin + 1
LC moved_bits       = selected_mat_count * hffs_per_mat
```

Thus an accepted LC-MOV range containing `N` mats moves
`N * hffs_per_mat` aggregate payload bits. In the evaluated configuration this
is `4N` bits. Range length does not multiply the request count, command count,
or modeled latency.

For the accepted initial singleton GB-MOV subset:

```text
GB moved_bits = hffs_per_mat
```

Count the transferred payload once. The source and destination endpoints do
not each contribute a separate payload width. In the evaluated configuration,
one GB-MOV therefore moves four bits.

`Request::size_bytes` is not applicable to LC-MOV or GB-MOV and is not an
authoritative or approximate movement-width field. Use `-1` as the canonical
not-applicable value for these request types. The implementation must express
this through a named not-applicable sentinel or predicate, or an equivalently
explicit contract, so that movement's intentional not-applicable value cannot
be confused with an accidentally uninitialized ordinary request. This
decision does not prescribe the exact C++ constant or predicate name.

Movement ingress must accept the explicit not-applicable representation and
reject any caller-supplied movement byte size. Do not silently overwrite an
arbitrary value, use the ordinary DRAM transaction size, or set
`size_bytes = ceil(moved_bits / 8)`. Existing positive-byte validation for
ordinary byte-sized requests remains unchanged. This decision does not change
the existing DDR4_PuD RowCopy, MAJ3, MAJ5, or NOT behavior.

Future movement accounting must derive and accumulate exact moved bits. It may
convert an aggregate bit count to a byte-rate presentation after accumulation,
but it must not round each request to an integral number of bytes. LC-MOV and
GB-MOV do not contribute to ordinary Read/Write byte-throughput metrics.

The HFF-width derivation is independent of movement Column semantics. It
decides how many payload bits one participating mat transfers, not which bit
positions a Column coordinate selects. Movement Column unit, valid range,
alignment, and mapping to the HFF-selected datapath remain unresolved.

Rationale

The evaluated movement width is not necessarily byte-aligned. A singleton
GB-MOV moves four bits, and an LC-MOV over an odd number of selected mats moves
`4N` bits in the evaluated organization. Encoding either value as
`ceil(moved_bits / 8)` would lose exactness: singleton GB-MOV would appear to
move eight bits, and every odd-length evaluated LC range would be overcounted
by four bits.

Current Ramulator request handling uses `size_bytes` only as a generic ingress
constraint requiring a positive value no larger than one DRAM transaction.
Address mapping, PuD routing, scheduling, command timing, completion, current
PuD statistics, and in-tree trace/plugins do not interpret it as PuD payload
width. Existing Read/Write throughput is computed from served request count
and the fixed DRAM transaction size rather than by summing `size_bytes`.
Current DDR4_PuD requests set a transaction-sized value only to satisfy this
generic ingress constraint and are excluded from Read/Write byte throughput.

Keeping a positive compatibility byte value for movement would therefore add
no modeling fidelity while exposing a misleading quantity to callbacks and
future accounting consumers. An explicit request-type-aware not-applicable
contract preserves ordinary-request validation without assigning fictitious
byte semantics to internal movement.

Derivation avoids duplicated request state. The accepted LC logical mat range
and GB singleton endpoints already provide movement geometry, while
`hffs_per_mat` is a property of the modeled hardware organization. Storing the
same result in each request would require consistency validation and could
become stale if geometry or future GB pairing rules changed. A stored width
may be reconsidered only if a later accepted consumer cannot access the
authoritative request geometry and standard/device configuration.

Width and Column selection answer independent questions. HFF count determines
the number of parallel payload bits transferred by one participating mat;
Column encoding determines which HFF-selected location or locations
participate. No byte-alignment or address-progression rule follows merely from
the four-bit evaluated width.

Evidence

MIMDRAM source facts:

- `docs/pud/references/mimdram-inter-column-data-movement.md` records that the
  evaluated MIMDRAM organization has four HFFs per mat, that the singleton
  LC-MOV walkthrough moves four bits through the selected mat's HFFs, and that
  the singleton GB-MOV walkthrough moves four bits through the inter-mat path.
- The same reference records that GB-MOV transfer width depends on the number
  of HFFs in a mat. It does not establish four HFFs as a property of DDR4 or
  every possible MIMDRAM organization.
- The reference gives Row and Column operands for LC-MOV and GB-MOV but does
  not establish a separate physical transfer-size field, a movement Column
  unit/alignment rule, wider GB range pairing, or Column progression.

Accepted architectural inference and project decisions:

- `docs/pud/decisions/mimdram-movement-range-and-placement.md` accepts one
  common lockstep LC-MOV sequence over a nonempty contiguous logical mat range,
  with one local HFF width moved by every selected mat. It accepts the inferred
  `4N`-bit aggregate for the evaluated four-HFF organization and the initial
  singleton same-chip directional-neighbor GB-MOV subset.
- `docs/pud/decisions/mimdram-movement-timing-resource-scope.md` accepts that
  LC range length does not multiply command count or latency.
- `docs/pud/decisions/mimdram-movement-numeric-timing-and-directed-edges.md`
  accepts fixed initial LC-MOV and GB-MOV timing graphs independent of
  movement width.

Repository evidence:

- `src/ramulator/base/request.h` defines `size_bytes` as an integral public
  request field and initializes it to `-1`.
- `src/ramulator/memory_system/impl/generic_dram_system.cpp` currently applies
  the positive, at-most-one-transaction size check before request-type routing.
- `src/ramulator/memory_system/pud_request_routing.h` routes current PuD
  requests from request-owned operands without consulting `size_bytes`.
- `src/ramulator/controller/impl/generic_ddr_controller.cpp` performs current
  PuD placement validation, sequencing, scheduling, and retirement without
  consulting `size_bytes`.
- `src/ramulator/controller/controller_base.cpp` computes Read/Write throughput
  from fixed transaction bytes and excludes PuD operations from that
  throughput. PuD completion and latency accounting do not consult
  `size_bytes`.
- In-tree command trace and controller plugins receive requests but do not
  consume or serialize `size_bytes`.

Open issues

- Movement Column unit, valid range, alignment, and mapping to the
  HFF-selected datapath remain unresolved. They are independent of the
  accepted HFF-width derivation.
- Refresh admission, maximum deferral, and deadline treatment for the accepted
  non-preemptive movement sequences remain unresolved. This decision does not
  select a new refresh policy.
- Column semantics and refresh admission/deferral remain candidate
  plan-shaping questions that must be resolved before final implementation-plan
  readiness is declared.
- Exact request departure, callback, modeled data-availability, and
  statistics-completion boundaries remain a later lifecycle decision.
- Exact movement counter names, accepted/completed accounting boundaries,
  moved-bit throughput presentation, and trace observability remain later
  statistics and diagnostics decisions. Any such accounting must preserve the
  exact-bit and ordinary-throughput exclusions accepted here.
- The exact configuration-tree path, parser/member representation, validation
  location, and C++ type for `hffs_per_mat` are implementation-plan details.
- A self-contained stored movement-width field may be reconsidered only if a
  future accepted consumer cannot derive width from authoritative geometry and
  configuration.
- Wider GB-MOV range pairing and its transfer-pair count remain outside the
  initial singleton subset and require a separate decision before a wider GB
  width can be derived.
