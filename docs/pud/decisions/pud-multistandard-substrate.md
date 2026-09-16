Status: G0 Accepted; scoped GDDR7 ACT-overhead exclusion Accepted;
GDDR7 G1/G2/G3/G4/G6 Open.

Question

What minimum architecture permits DDR4, GDDR7, and HBM3 to share the current
PRADA/MIMDRAM PuD execution substrate while preserving DDR4 behavior and
keeping unresolved physical profiles and timing explicit?

Decision

**Accepted — G0 common architecture (2026-09-16).** Implementation
authorization is limited to Phase 1, the DDR4-preserving common-substrate
extraction. The separately scoped GDDR7 ACT-overhead exclusion below is the
only additional Accepted target choice. No GDDR7 geometry, A/B/C calibration
policy, command encoding, reception anchor or resource scope is accepted.
Existing Accepted DDR4 decisions remain authoritative and are not superseded.

1. Keep one Request/occurrence protocol, one invocation execution model, and
   one implementation of footprint ownership, compute allocation, movement
   acquisition, local state, recovery and exact-once completion. Keep one
   PuDTrace dependency scheduler and the existing arithmetic/lowering code.
   Preserve the Accepted mat-footprint policy and no-SALP restriction.
2. Generalize the hierarchy portion of canonical locations to identify the
   actual standard's path through Bank, scoped by the retained resolver and
   routing association. Keep internal Subarray/LocalRow and mat/group identity
   separate. Do not introduce fictional Rank/BankGroup fields or reinterpret
   HBM3 PseudoChannel/Sid as DDR4 Rank/Chip. Preserve the DDR4 public projection
   and physical mapping exactly through its binding.
3. Supply a small standard binding through existing DRAMSpec/configuration
   facilities plus only the missing PuD inputs: semantic command IDs and
   metadata; local/occurrence timing and recovery anchors; shared constraint
   scopes and publication; bus occupancy/edge legality; conventional recovery
   integration; placement selection and control-unit/engine-pool association.
   Derive the eventual API from these consumers; do not introduce a second
   DRAM-spec framework or a general programmable sequence language.
4. Extract reusable PuD admission/allocation/candidate/issue integration from
   GenericDDR so the existing GenericDDR, GDDR7 and HBM34 controllers can use
   it while retaining their ordinary arbitration and bus/edge behavior.
   Keep Device invocation dispatch common. Replace DDR4-only timing-scope
   assumptions at that boundary, without publishing local PRE recovery into
   disjoint contexts. Thin generated standard registrations are permitted;
   independently copied controller/device state machines are not.
5. Factor common Python PRADA/movement declarations from DDR4 base timing,
   organization and calibration. Preserve current DDR4 registrations, numeric
   command IDs/order, configuration and generated behavior. Continue using
   shared command templates and regenerate generated files from their sources.
6. Select independently named coordinated target placement profiles only
   after explicit geometry/routing approval. Expose the selected C++ profile
   to higher layers; do not maintain an independent Python mat map. Preserve
   DDR4 defaults, legacy trace bytes and both existing GEMV schedules. Review
   target trace encoding and placement enumeration before their first use.

The first implementation phase is a behavior-preserving DDR4 extraction.
GDDR7 and HBM3 bindings remain gated. No target may become executable with
temporary DDR4 geometry, cycle counts, or a partially protected movement path.

### Accepted GDDR7 ACT-overhead exclusion (2026-09-16)

Accepted explicitly by the user on 2026-09-16. Scope: the GDDR7 target's
proposed PRADA+MIMDRAM PuD timing model only.

> Do NOT apply the MIMDRAM <0.5% ACT-latency overhead/envelope to the GDDR7 PuD timing model.
>
> Do NOT add a separate +0.5% sensitivity case.

This excludes the envelope from both the GDDR7 timing model and sensitivity
configurations. Under the still-unaccepted G2 Policy A, the unscaled candidate
phase quantization remains `A*=16, A=8, A_S*=58, A_S=50, N=62 CK4`.
These values are conditional on that policy and the illustrative 571-ps CK4;
they do not constitute acceptance of Policy A.

**G2 as a whole remains Open.** Policy A/B/C, reception/completion anchors
and other timing semantics still require explicit review. G1/G3/G4/G6 also
remain Open. This sub-decision neither changes DDR4's accepted treatment nor
authorizes GDDR7 PuD implementation.

Rationale

The existing ownership/completion machinery already resides mostly in shared
Request, ControllerBase and Device code. The remaining coupling is concrete:
six-coordinate placement structs, fixed profile selection, GenericDDR tick
integration, Bank-edge local timing, Channel-only PuD shared publication and
single-bus occupancy. Small bindings address those points without forking
the substrate or redesigning unrelated conventional DRAM behavior.

Copying the DDR4 classes would duplicate sequencing, conflict and callback
semantics. Replacing all conventional controllers with one new controller
would broaden risk and could discard HBM edge pairing or GDDR7 RCK handling.
The proposed factoring preserves these existing controllers and shares only
the PuD policy/integration machinery they need.

Separating standard organization from physical placement also prevents a
successful hierarchy conversion from being mistaken for physical evidence.
Existing memory-standard presets cannot determine mats, HFFs or GB topology.

The GDDR7 overhead exclusion reflects the evidence boundary: MIMDRAM's
<0.5% result comes from its evaluated fine-grained activation implementation,
not a measurement of the proposed GDDR7 PRADA+MIMDRAM hybrid. Applying that
envelope to the GDDR7 baseline would introduce an unsupported target-specific
modeling assumption. Separately, the user explicitly chose not to include a
+0.5% sensitivity configuration. That scope choice does not imply that
sensitivity analysis itself is scientifically invalid. Neither choice asserts
physically zero hybrid overhead.

Evidence

- [GDDR7 Phase-2 modeling reference](../references/gddr7-pud-modeling-reference.md)
  records the 2026-09-16 G1/G2/G3/G4/G6 investigation, supplied geometry checks,
  timing/resource alternatives and conventional-baseline gaps. It selects no
  policy; project status is recorded here.
- The user's explicit instruction on 2026-09-16 accepts only the GDDR7
  no-ACT-envelope/no-sensitivity sub-decision above. The
  [MIMDRAM technical reference](../references/mimdram-inter-column-data-movement.md#12-fine-grained-mat-access-structures)
  records the evaluated <0.5% ACT-latency evidence and its hybrid-applicability
  limitation.
- [Source audit](../references/pud-multistandard-substrate-audit.md), especially
  §§2–5, identifies each current consumer and the actual standard structures.
- [Unified DDR4 substrate](ddr4-pud-unified-substrate.md),
  [placement](mimdram-addressing-geometry-and-payload.md),
  [execution](mimdram-movement-execution-ownership-and-device.md), and
  [timing/resources](mimdram-movement-timing-and-resource-model.md) establish
  the existing contracts being preserved, including disjoint movement progress.
- [PRADA portability methodology](../references/ddr4-pud-timing-reference.md#11-portability-of-the-timing-methodology)
  explicitly requires phase revalidation instead of copying DDR4 numbers.
- [Operation lowering](pud-operation-physical-lowering.md) separates local-row
  allocation from placement; [GEMV](pud-gemv-macro-contract.md) fixes the two
  current arithmetic schedules and dependency completion boundary.

Open issues

### Proposed — GDDR7 target choices (not Accepted)

The following proposals preserve the suggestions from the initial GDDR7
investigation in the decision document. They are review items, not project
authority or implementation authorization. Only the overhead exclusion in
Decision above is newly Accepted. Evidence, calculations and alternative
consequences are in the [GDDR7 reference](../references/gddr7-pud-modeling-reference.md).

| Gate / item | Proposed choice | Alternatives / trade-off still Open |
| --- | --- | --- |
| G1 modeled placement | Begin with one `GDDR7_16Gb_x8` Channel slice, 32 mats/subarray, 512×512 mats, H-equivalent=8, contiguous 512-row subdivisions, no remapping/reserved offset; use the reference's invertible byte-to-mat/eight-cell-group example with CacheLineInterleave/RoBaRaCoCh. | Source dimensions do not uniquely fix mapping or prove GDDR7 internal wiring. Other permutations fit the same capacities; vendor-faithful placement needs target-specific evidence. |
| G1 GB successor topology | Ascending local mat order with directed singleton edges `m→m+1`, m=0..30; no reverse, wraparound or cross-channel path. | Numerical ordering as physical adjacency remains a modeling convention, not a consequence of page size. |
| G2 phase policy | Policy A for an exploratory port, using unscaled physical phase times. | B preserves aggregate calibration by changing tSR; C waits for target circuit calibration. No policy is selected. The Accepted overhead exclusion applies independently of this choice. |
| G2 anchors | Final-reception phase anchors; reception-adjusted directed edges exactly once; terminal recovery from final PRE reception. | Physical phase start versus command issue/reception and completion semantics require review together with command occupancy. |
| G3 engine pool | One configurable pool per actual x8 Channel/controller, shared across its 16 Banks; E=8 as a proposed comparison setting. | Final engine count remains Open. Per-bank pools partition capacity; package-wide pooling requires additional association across controllers. |
| G3 RCK treatment for movement | RD_MOV/WR_MOV use internal transfers without starting RCK, updating last external read, or requiring RCK toggling; retain column-bus contention with RCK commands and preserve ordinary RCK modes. | Applying ordinary read-clock/data rules would add external-I/O costs. Internal-transfer independence is an assumption, not established GDDR7 circuitry. |
| G3 current constraints | Carry over compute activation-current exclusion and omission of movement-specific current constraints, explicitly labeled uncalibrated. | A Channel ACT-current class including ordinary and selected PuD activations, using nRRD as a proxy, would change GB and inter-bank spacing. Neither policy is physically validated for the hybrid. |
| G3 shared publication | Preserve ordinary incoming recovery/refresh scope; publish shared bus and Channel nPPD spacing for invocation PRE, keeping its recovery local rather than publishing Bank/sibling nRP/nRPD deadlines. | Exact application to new command identities remains Open; extending local PRE into shared histories would restrict disjoint progress. |
| G4 movement intervals | Retain the LC/GB logical sequences and occurrence-specific graph; use the reference's nRCDRD/nRTPSB/nRAS/nRP/nWR analogues, including nRAS as the destination restoration barrier. | Ordinary nRCDWR readiness is a different semantic interval. These mappings are project approximations, not GDDR7 movement calibration. |
| G4 relocation | Retain FIGARO-derived 1 ns for LC and GB as a labeled assumption; quantize independently to 2 CK4 at 571 ps. | Target-path calibration is unavailable; the FIGARO path is related but different. |
| G4 concurrency/close | Bind the Accepted common physical-mat-footprint policy, no-SALP and protected recovery without an added GB-link owner; retain abstract mat-selective close and LC source-HFF validity. | Common policy is already Accepted; its GDDR7 realization/fidelity remains under review. No supplied evidence establishes a target-specific shared-link rule. |

**Proposed GDDR7 command resources — not Accepted**

| PuD command role | Proposed bus / occupancy | Scope and limitation |
| --- | --- | --- |
| A, A*, A_S, A_S* | Channel row bus / 2 CK4 each | Invocation-local physical phases; ACT-like reception approximation, no established GDDR7 encoding or extra mat-target enqueue cycle. |
| N | Channel row bus / 1 CK4 | Proposed command envelope independent of physical tN; longer encoding would change contention and issue offsets. |
| ACT_MOV | Channel row bus / 2 CK4 per endpoint | Two visible GB endpoint activations. |
| RD_MOV / WR_MOV | Channel column bus / 2 CK4 each | Internal data movement; shares issue resources with ordinary columns and RCK commands. RCK behavior is separately proposed above. |
| PuD PREpb, including LC source PRE | Channel row bus / 1 CK4 | Invocation-footprint close; no PREab substitute or Bank-wide local recovery publication. |

Ordinary command resources remain as documented in the reference. PuD
engine/footprint acquisition and completion use the common substrate; movement
consumes no compute engine. Neither this table nor those common mechanisms
establish a physical GDDR7 PuD command encoding.

**Proposed/Open G6 dispositions — not Accepted**

Classification vocabulary: A irrelevant to the selected scope; B bounded
approximation; C must fix before PuD; D source evidence needed.

| Issue | Proposed disposition | Open alternative / scope consequence |
| --- | --- | --- |
| Approximate preset | B for explicitly labeled exploratory/CI use of the exact preset/overrides. | D for vendor-calibrated performance claims. B bounds configuration and claims, not a known error bar; a part/speed-bin timing table remains missing. This proposal adds no ACT-envelope sensitivity case. |
| PREab gaps | C: resolve legality/recovery before the general mixed conventional/PuD binding; D for exact source-backed repair values/anchors. | Obtain applicable JESD239/vendor relationships or explicitly approve a conservative repair over every affected Bank, including incoming ACT/read/write/AP and outgoing ACT/refresh/maintenance. Exact repair is Open; copying nRTPSB mechanically is not established. |
| PREab restricted scope alternative | Open alternative to repair: prohibit PREab and every path generating it. | This also excludes all-bank refresh prerequisites on open Banks and needs enforceable configuration/validation. It would narrow the Phase-2 traffic invariant; it is not the proposed general-binding path. |
| RFM | Proposed exclusion from the initial experimental workload/maintenance scope, with full-scope conflict protection retained; A only under an explicit no-RFM contract. | Exclusion must cover manual priority injection and managers/plugins, not just automatic defaults. If RFM traffic remains supported, D/C: obtain adequate incoming/outgoing rules and validate both scopes. Ordinary REF interaction remains required. |

### Open — GDDR7 gates

G1/G2/G3/G4/G6 are **Open as wholes**. Only the GDDR7 no-ACT-envelope /
no-sensitivity sub-decision is newly Accepted. User review must resolve the
profile/topology, A/B/C and anchors, command/engine/current/RCK resources,
movement mapping/relocation, and PREab/preset/RFM dispositions before their
first code consumers. A separate implementation authorization is still
required. No 0.5% overhead or sensitivity question remains open for GDDR7.

The supplied geometry yields consistent dimension counts and H-equivalent=8,
but does not make the complete physical placement deterministic. HBM3's
supplied page claims remain evidence for later investigation; no HBM3 profile
is selected. G5/G7 remain outside this target-gate review.

G0 is resolved by the user acceptance on 2026-09-16. The [audit gate table](../references/pud-multistandard-substrate-audit.md#6-decision-gates-and-required-information)
records unresolved target profiles (G1), compute calibration/anchors (G2),
hierarchy/resources/buses (G3), movement portability (G4), trace encoding (G5),
base-standard adequacy (G6), and GEMV placement (G7), with first consumers and
alternatives. Neither DDR4's calibration nor its physical profile answers
these gates. Physical target delivery, mat-selective PRE and disjoint GB
datapath fidelity retain their documented limits. No energy, SALP, new
topology, functional payload simulation, or new GEMV baseline is proposed.
