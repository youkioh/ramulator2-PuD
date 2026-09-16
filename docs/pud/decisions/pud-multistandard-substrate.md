Status: G0 Accepted; GDDR7 G1/G2/G3/G4 Accepted; G5/G6/G7 Open.

Question

What minimum architecture permits DDR4, GDDR7, and HBM3 to share the current
PRADA/MIMDRAM PuD execution substrate while preserving DDR4 behavior and
keeping unresolved physical profiles and timing explicit?

Decision

**Accepted — G0 common architecture (2026-09-16).** Phase 1's DDR4-preserving
extraction is complete. The common execution-model amendment below and GDDR7
G1/G2/G3/G4 are Accepted; G6 remains Open with its existing candidate.
G5/G7 remain Open for target trace/hierarchy and GEMV placement portability.
HBM3 target choices are unchanged. These acceptances authorize no production
implementation; the common finite-engine correction must precede target binding.
Older DDR4 authorities remain current except for the explicitly superseded
finite-engine-accounting clauses listed below.

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
   integration; placement selection and routing association.
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

### Accepted common execution model — no finite control-engine capacity (2026-09-16)

This common policy applies to **DDR4 PuD, GDDR7 PuD and future HBM PuD**.
The modeled path is logical PuD operation -> physical PuD primitives -> DRAM
command sequences. Model physical hierarchy/placement, mat/subarray/Bank
footprints and conflicts, command resources and timing, no-SALP where applicable,
movement dependencies, conventional/PuD protection, terminal recovery,
frontend/dependency ordering and independently modeled queue/resource limits.

Finite SIMDRAM/MIMDRAM bbop/microProgram control-unit throughput capacity is
**outside the performance abstraction**. RowCopy, MAJ3, MAJ5, NOT, NOT_COPY,
LC-MOV and GB-MOV have **no finite control-engine charge**. There is no primitive
engine count and no engine-pool scope. Do not impose E=8 or any other finite E
as a runtime primitive concurrency limit, multiply E by Banks, or create
per-Bank pools. This omits a bottleneck; it does not assert infinite physical
hardware resources. MIMDRAM's reported eight engines remain prior-work
architecture/area evidence, not this simulator's primitive performance parameter.

Do not introduce parent ADD/MUL/movement contexts, bbop IDs, OPERATION
directives, completion joins or cross-output GEMV grouping merely to retain E.
The investigated parent-context model is rejected. Existing arithmetic lowering,
GEMV calls, reduction ordering, physical traces and CHAIN dependency semantics
continue without bbop engine identity. G5 concerns target trace/hierarchy
representation and compatibility; G7 concerns target GEMV placement/mapping
portability. Neither depends on finite-engine modeling.

**Narrow DDR4 amendment.** Supersede only these finite-engine clauses:

- [Execution/ownership](mimdram-movement-execution-ownership-and-device.md):
  Resources and admission's E/default/pool and atomic engine-plus-range charge;
  Recovery, maintenance, and completion's engine retention/release; the
  compute-versus-movement engine distinction and associated rationale.
- [Unified DDR4 substrate](ddr4-pud-unified-substrate.md): selectable
  compute-engine capacity and inherited first-fit finite-engine allocation.
- [Timing/resources](mimdram-movement-timing-and-resource-model.md): retained
  compute-engine constraint, E=8/recovery cross-reference and engine waiting.
- [Mat-target transport](mimdram-mat-target-transport-abstraction.md): retained
  independent E=8 default and inherited engine ownership.

Those documents contain reciprocal amendments; their other clauses remain
Accepted. Physical footprint ownership/conflicts, no-SALP, command and movement
timing, placement, arithmetic/GEMV dependencies, terminal recovery and
conventional/PuD protection are unchanged. The completed Phase-1 implementation
still charges one engine per compute Request through recovery and none to
movement. That is temporarily stale implementation behavior, not the desired
architecture, and remains the basis of its frozen historical results until
a separately authorized common code correction establishes a new baseline.
Completed older plans and the original source audit likewise describe that
implementation; they do not restore superseded engine authority.

#### Future finite-engine reintroduction requirements

Reintroduction requires a **new explicit architecture/modeling decision** and
a dedicated audit of SIMDRAM, MIMDRAM, Proteus and later architectures explicitly
modeling the same bottleneck. For each relevant work, independently establish:

1. What consumes a context: bbop, complete operation, primitive, partition or other entity?
2. Its scope: controller, Channel, Rank, Bank, subarray or another unit.
3. The number of contexts.
4. The allocation event.
5. The release event.
6. Whether movement consumes the same resource.
7. Interaction with BLP.
8. Interaction with SALP.
9. Whether one context controls multiple Banks/subarrays.
10. The actual hardware/control mechanism enabling any such fan-out.
11. Whether independent operations progress concurrently.
12. Whether the performance simulator implements finite occupancy/backpressure.
13. Whether engines appear only in architectural prose or area accounting.
14. How published performance evaluation accounts for capacity.
15. The public source/code supporting each claim.

Expose ambiguity, missing mechanisms, architecture/evaluation inconsistencies
and unavailable implementation details; do not repair them silently. If no
complete prior-work model is recoverable, label any proposed finite model
**NEW PROJECT MODELING ASSUMPTION**, not “MIMDRAM engine model.” Evaluation
must justify, and preferably sensitivity-sweep, count, scope, allocation
granularity, release lifetime, movement accounting and BLP/SALP interaction.
Eight reported engines alone cannot restore E=8. E×Banks, one engine per
primitive/Bank, or arbitrary multi-Bank parent control are forbidden shortcuts
unless a new audit independently establishes that exact behavior.

### Accepted GDDR7 ACT-overhead exclusion (2026-09-16)

Accepted explicitly by the user on 2026-09-16. Scope: the GDDR7 target's
proposed PRADA+MIMDRAM PuD timing model only.

> Do NOT apply the MIMDRAM <0.5% ACT-latency overhead/envelope to the GDDR7 PuD timing model.
>
> Do NOT add a separate +0.5% sensitivity case.

This excludes the envelope from both the GDDR7 timing model and sensitivity
configurations. It neither changes DDR4's accepted treatment nor claims
physically zero hybrid overhead. G2 below now accepts Policy A and its anchors.

### Accepted G1 — GDDR7 placement and provisional PA mapping (2026-09-16)

Use one modeled x8 GDDR7 Channel slice: 512×512-cell mats, 32 mats/subarray,
512 rows/subarray, eight HFF-equivalent transfer positions/mat and 64 groups
per mat row. HFF-equivalent=8 is a derived transfer-width model, not a claim
of eight physical MIMDRAM HFFs per GDDR7 mat. Subdivide rows contiguously:
`Subarray = Row / 512`, `LocalRow = Row % 512` (integer division).

Authoritative PuD placement remains **hierarchy through Bank + Row + MatRange +
optional Group**. The PuD trace/Request path does not require a physical
byte address to execute an operation; this does not select the later G5 encoding.

Retain the existing DDR4-style Ramulator integration,
`CacheLineInterleave + RoBaRaCoCh`, for ordinary physical addresses in the
initial GDDR7 implementation. This is a **provisional compatibility mapping**,
not actual NVIDIA GPU PA mapping, verified GDDR7 bank/row wiring, or a
source-supported GDDR7 hash/XOR map. The user-supplied GPUHammer evidence of
256-B GPU bank/row granularity is realistic-address-mapping evidence; it does
not establish a 256-B channel-interleave setting. Do not force it into either
mapper. Exact GPU bank hash/XOR is unresolved and deferred. A later realistic
PA mapper may replace this compatibility path without changing the Accepted
PuD internal geometry.

Retain directed local-mat GB edges `m -> m+1`, m=0..30, with no reverse,
wraparound or cross-channel edge. This is an explicit project topology
convention, not source-established GDDR7 wiring.

### Accepted G2 — GDDR7 PRADA timing (2026-09-16)

Use **Policy A**: retain the currently adopted physical PRADA phase intervals
and independently quantize each into GDDR7 CK4; use conventional GDDR7 PRE
recovery separately. Do not recompute tSR to preserve DDR4 aggregate latency.
At 571 ps/CK4 in the current project GDDR7 evaluation baseline
(`GDDR7_28000_PAM3`), use `A*=16, A=8, A_S*=58, A_S=50, N=62 CK4`.
The Accepted no-envelope/no-+0.5%-sensitivity policy remains in force.

Anchor physical/timing intervals consistently to **command final reception**.
Convert to first-issue spacing exactly once:
`I_follow - I_pre >= interval + occupancy_pre - occupancy_follow`.
Do not double-apply reception adjustment between serialized Device edges and
occurrence-specific delays. Terminal recovery ends at final PRE reception plus
nRP (`I_PRE + occupancy_PRE - 1 + nRP`). These are project timing semantics,
not target circuit calibration.

### Accepted G4 — GDDR7 movement timing (2026-09-16)

Keep the existing LC-MOV and GB-MOV logical sequences and the following
final-reception intervals; apply G2's issue conversion once.

| Sequence | Dependency | Interval |
| --- | --- | --- |
| LC | ACT(src) -> RD_MOV(src) | nRCDRD |
| LC | RD_MOV(src) -> PRE(src) | nRTPSB |
| LC | ACT_MOV -> applicable PRE | nRAS |
| LC | PRE(src) -> ACT(dst) | nRP |
| LC | ACT(dst) -> WR_MOV(dst) | nRAS |
| LC | WR_MOV(dst) -> PRE(dst) | nRELOC + nWR |
| GB | Source ACT_MOV -> RD_MOV | nRAS, anchored to source ACT occurrence, never the later destination ACT |
| GB | Destination ACT_MOV -> WR_MOV | nRAS |
| GB | ACT_MOV -> applicable PRE | nRAS, retained local minimum-active constraint |
| GB | RD_MOV -> WR_MOV | nRELOC |
| GB | WR_MOV -> PRE | nWR |
| LC/GB | Terminal PRE recovery | nRP |

Retain `tRELOC=1 ns`, independently quantized to **2 CK4 at 571 ps/CK4**.
Retain physical-mat-footprint conflicts, disjoint compute/LC/GB progress subject
to shared modeled resources, no-SALP, protected recovery, abstract mat-selective
close and LC source-HFF retention. Add no Bank-wide movement owner or GB-link
owner. These timing analogues and the relocation assumption do not establish
GDDR7 internal-path calibration.

### Accepted G3 — GDDR7 command resources and common execution model (2026-09-16)

Finite microProgram-engine capacity is not modeled; primitive engine count is
none, pool scope is not applicable, and compute/LC/GB admission has no finite
engine charge, under the common policy above. No unrelated G3 blocker remains.
Retain the already resolved command-resource/RCK rules:

| PuD command role | Accepted bus / occupancy | Scope and limitation |
| --- | --- | --- |
| A, A*, A_S, A_S* | Channel row bus / 2 CK4 each | Invocation-local physical phases; ACT-like reception approximation, no established GDDR7 encoding or extra mat-target enqueue cycle. |
| N | Channel row bus / 1 CK4 | Selected command envelope independent of physical tN; longer encoding would change contention and issue offsets. |
| ACT_MOV | Channel row bus / 2 CK4 per endpoint | Two visible GB endpoint activations. |
| RD_MOV / WR_MOV | Channel column bus / 2 CK4 each | Internal data movement; shares issue resources with ordinary columns and RCK commands. RCK behavior is retained below. |
| PuD PREpb, including LC source PRE | Channel row bus / 1 CK4 | Invocation-footprint close; no PREab substitute or Bank-wide local recovery publication. |

Ordinary command resources remain as documented in the reference. The common
physical invocation machinery remains the execution basis, with no finite
control-engine accounting for either compute or movement. These bus choices
do not establish a physical GDDR7 PuD command encoding.

RD_MOV/WR_MOV remain internal transfers: no RCK start, external-read-history
update or requirement for RCK toggling; retain column-bus contention with RCK
and ordinary mode behavior. Carry over compute activation-current exclusion
and omission of movement-specific current constraints as uncalibrated
assumptions. Preserve incoming conventional recovery/refresh scope; publish
shared bus and Channel nPPD for invocation PRE, with local recovery rather
than Bank/sibling nRP/nRPD publication.

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

The finite-engine amendment addresses an abstraction mismatch: prior-work
engines execute bbop/microProgram contexts, whereas the current code charges
physical compute primitives and excludes movement. The papers and inspected
public artifacts do not supply a complete finite-control model connecting
those contexts to evaluated BLP/SALP. Omitting that bottleneck explicitly is
the selected performance abstraction; neither primitive E=8 nor a speculative
parent-context model is justified by the reported count alone.

G1 separates explicit PuD placement from replaceable ordinary PA compatibility;
GPUHammer granularity alone cannot determine either mapper's bit functions.
G2 preserves individual physical phases rather than compensating tSR for a
different PRE duration. G4 retains the existing movement dependency meaning
and concurrency contract with independently quantized target intervals.

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
- The user's explicit instructions on 2026-09-16 accept the common finite-engine
  scope amendment and G3, in addition to GDDR7 G1/G2/G4, and
  preserve the earlier no-ACT-envelope/no-sensitivity sub-decision. The
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

### Proposed G6 final choice — Open pending approval

Use `GDDR7_16Gb_x8 / GDDR7_28000_PAM3` without timing overrides as the fixed
**project GDDR7 evaluation baseline**, with the following proposed PREab
correction. This is an architecture-evaluation configuration, not a
vendor-calibrated timing model or a claim of known timing error bounds.

**PREab:** keep all-bank precharge and ordinary REF support. Add the missing
Channel-scoped conventional timing edges below, using nominal final-reception
intervals and one reception-to-issue conversion. Existing edges remain.

| Preceding -> following | Proposed interval | Conservative project meaning |
| --- | --- | --- |
| ACT -> PREab | nRAS | Every affected Bank's minimum active time |
| RD -> PREab | nRTPSB | Apply the existing per-bank read-close floor across all affected Banks; not a JEDEC all-bank identity |
| WR -> PREab | nWL+nBL+nWR | Preserve conventional write delivery/recovery |
| RDA -> PREab | nRTPSB+nRP | Wait for full modeled AP recovery before redundant all-bank close |
| WRA -> PREab | nWL+nBL+nWR+nRP | Same conservative AP drain rule |
| REFpb -> PREab | nRFCpb | Drain per-bank refresh before a close covering that Bank |
| RFMpb -> PREab | nRFMpb | Structural recovery guard using the existing placeholder; no physical calibration claim |
| PREab -> ACT, REFpb, RFMpb | nRP | Recovery covers all Banks; existing PREab -> REFab/RFMab=nRP is retained |

Preserve existing REFab/RFMab -> PREab recovery and nPPD spacing. Extend
conventional PREab nRP and maintenance recovery into PuD opening commands
when the binding is implemented; keep invocation-local PRE recovery local.
Common protected ownership blocks PREab/REF/RFM that intersect any active or
recovering invocation. This is a small timing-definition repair, not a
priority change or a JEDEC/vendor-correctness assertion. The full AP drain
rule may add conservative delay; no DDR4 change is proposed.

**RFM policy B:** retain command plumbing, manual injection capability and
all-bank/per-bank PuD conflict protection. Generate no RFM in the selected
evaluation workload/maintenance policy: no RFM-producing manager/plugin or
manual RFM in those evaluation inputs. Verify zero RFM in evaluation traces;
separate injected-command safety tests remain permitted. Make no validated
physical-timing claim for RFM latency. No command rejection/removal is needed.

Policy A would include both RFM scopes in validated timing and require
adequate incoming/outgoing rules plus physical calibration evidence unavailable
here. Policy B preserves safety/reachability without making those claims;
RFM latency remains outside the evaluated timing scope. Ordinary REFab/REFpb
and their interaction with PuD remain inside it.

### Open — GDDR7 gates

GDDR7 **G1/G2/G3/G4 are Accepted; G6 is Open** with its existing conservative
PREab repair plus baseline/RFM policy B candidate. G0 remains Accepted.
Complete the common finite-engine code correction before GDDR7 binding;
resolve G6 before its timing/issue consumers and obtain separate implementation
authorization. No ACT-envelope or sensitivity question remains open.
Exact realistic GPU PA hashing is deferred outside
the provisional G1 mapping; target physical fidelity remains limited as stated.

G5/G7 remain Open for target trace/hierarchy compatibility and GEMV physical
placement portability, respectively; neither depends on engine identity or
cross-output grouping. HBM3's gates and supplied page
evidence remain for later investigation; GDDR7 acceptance does not select
an HBM3 profile. The
[audit gate table](../references/pud-multistandard-substrate-audit.md#6-decision-gates-and-required-information)
retains first-consumer context; current GDDR7 status is authoritative here.
No energy, SALP, functional payload simulation or new GEMV baseline is proposed.
