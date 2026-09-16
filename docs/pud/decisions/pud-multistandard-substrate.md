Status: Accepted

Question

What minimum architecture permits DDR4, GDDR7, and HBM3 to share the current
PRADA/MIMDRAM PuD execution substrate while preserving DDR4 behavior and
keeping unresolved physical profiles and timing explicit?

Decision

Accepted by the user on 2026-09-16 (G0). Implementation authorization is limited
to Phase 1, the DDR4-preserving common-substrate extraction. Nothing in this document
accepts new target geometry, calibration, command encoding, or resource scope.
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

Evidence

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

G0 is resolved by the user acceptance on 2026-09-16. The [audit gate table](../references/pud-multistandard-substrate-audit.md#6-decision-gates-and-required-information)
records unresolved target profiles (G1), compute calibration/anchors (G2),
hierarchy/resources/buses (G3), movement portability (G4), trace encoding (G5),
base-standard adequacy (G6), and GEMV placement (G7), with first consumers and
alternatives. Neither DDR4's calibration nor its physical profile answers
these gates. Physical target delivery, mat-selective PRE and disjoint GB
datapath fidelity retain their documented limits. No energy, SALP, new
topology, functional payload simulation, or new GEMV baseline is proposed.
