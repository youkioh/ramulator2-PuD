Status: Accepted

Question

How are GEMV and shared-K GEMM workloads generated on the PuD substrate: how
do reductions merge mat-local fragments over the directed GB topology, which
evaluation schedules, length domain, and completion boundary apply, and how
are outputs placed, packed, fused, and assigned to CHAINs on each target?

Decision

This is the canonical workload-layer authority. It composes the accepted
substrate without changing it: locations follow the
[geometry decision](mimdram-geometry-and-placement.md), execution and timing
follow the [execution decision](mimdram-execution-and-timing.md), target
bindings, the common `PUD_TRACE 2` trace, and frontend admission follow the
[multistandard decision](pud-multistandard-substrate.md), and single-operation
row lowering follows the [physical lowering decision](pud-operation-physical-lowering.md).
Existing primitives, controller scheduling, timing parameters, and no-SALP
behavior are unchanged by any workload rule below.

**Direct generation**

The project does not reproduce MIMDRAM's generic compiler or accept arbitrary
compiler-generated `bbop_mov` operations. It generates the required reduction
request streams directly. Solving the complete generic MIMDRAM
movement-routing problem is not a prerequisite.

**Low-level GB movement unit**

Retain the singleton directed GB request as the project's source-defensible
low-level inter-mat movement unit:

```text
one source mat
    ->
one profile-supported directed neighboring destination mat
```

Each request transfers one HFF-width source/destination group, with the
geometry decision's ordered position correspondence and shared placement
context. This is a supported conservative subset/lowering unit. It is **not** a
claim that MIMDRAM's published GB-MOV interface is singleton-only: that
interface accepts source and destination logical mat ranges, whose wider-range
execution is not fully specified by the cited source. The profile-defined
directed GB topology is authoritative. Do not invent reverse, wrapping,
cross-chip, or arbitrary-distance GB edges.

`LogicalMatID` denotes the simulator's global mat identifier across the chips
of a placement-profile bank/subarray context. Under that profile and the
retained external context it identifies a modeled physical mat; the bare
integer is not unique across Banks, Ranks, or subarrays. The DDR4 profile
decodes it to `(Chip, LocalMat)` using `16 * Chip + LocalMat`. This is not a
claim about vendor-secret physical mat numbering. Physical/modeled GB
adjacency comes from the profile topology; consumers must not reconstruct it
from numerical ID adjacency. Consecutive IDs at a chip boundary, for example,
do not create a GB edge.

**Direct reduction placement**

Divide each reduction input into mat-local fragments according to the
accepted placement profile. Within each connected GB domain, arrange the
participating fragments in the forward order of the directed topology. Select
a reduction sink reachable through forward neighboring edges; do not generate
a schedule requiring a reverse GB edge. For the linear chip-local topology,
reduce from lower local mats toward the highest selected local mat. For K
consecutive participating mats in one connected linear domain, the conceptual
forward fold is:

```text
fragment0 -> mat1, ADD
accumulated01 -> mat2, ADD
...
accumulated[0..K-2] -> mat[K-1], ADD
```

Here `mat0` through `mat[K-1]` denote the selected consecutive mats in
topology order, not necessarily local IDs starting at zero. Each arrow copies
the current full partial fragment using repeated supported one-hop requests;
the destination ADD combines it with that mat's local fragment. After the
inter-mat fold, the source-described intra-mat LC-MOV + ADD tree runs in the
sink; a single participating mat needs only the intra-mat reduction. The extension
from MIMDRAM's two-mat example to this K-mat fold is an accepted project
orchestration choice, not a merge schedule supplied by MIMDRAM; it adds no
interconnect. Dependent work remains subject to the execution decision's
producer-completion boundary.

If selected fragments cannot be connected by the directed topology, do not
invent reverse or cross-chip GB and do not assume arbitrary multi-hop
routing; placement must avoid such unreachable moves within a reduction
domain. Each connected chip-local domain produces its own H residual
elements (four for DDR4). Disconnected domains finish separately and are combined by the host
under the execution decision's completion boundary; H residuals per domain
does not mean H residuals for the whole workload. Forward multi-hop through
intermediate temporary rows is structurally expressible by composing one-hop
transfers but is not required by the selected consecutive-mat placement;
its temporary-row/dependency semantics and generic multi-hop `bbop_mov`
routing are neither source-established nor accepted.

**GB movement-count derivation**

Let `L` be the elements in one source mat fragment, `H` the HFF/interconnect
width in element positions per bit-plane transfer (`H = 4` for DDR4), and `w`
the represented bit width moved at that reduction stage. One low-level GB
request transfers one bit from each of H element positions, not H complete
w-bit elements. For a full one-hop transfer of an L-element fragment, with L
divisible by H:

```text
N_GB_one_hop = (L / H) * w
```

For `L = 512`, `H = 4`:

```text
N_GB_one_hop = 128 * w
```

For the K-mat forward fold, with L elements in each transferred partial
fragment and constant represented width:

```text
N_GB = (K - 1) * (L / H) * w
```

If represented width changes between fold stages:

```text
N_GB = (L / H) * sum(w_j)
```

The sum runs over the K-1 inter-mat fold transfers, with `w_j` the width
actually moved at transfer j. These are project derivations, not equations explicitly provided by
MIMDRAM, counting the conservative singleton lowering requests, not ISA instructions, ranged-command
parallelism, elapsed cycles, or MIMDRAM's minimum GB-MOV command count. Input
precision alone must not be substituted for the represented width of an
accumulated fragment.

**GEMV evaluation baselines**

Exactly two active evaluation baselines use the existing arithmetic and
timing: `MIMDRAM-InterMatFirst` and `MIMDRAM-IntraMatFirst`. Each supports
INT8, FP8-E4M3 and FP8-E5M2. CLI profiles are the baseline name followed by
`-int8`, `-fp8-e4m3`, or `-fp8-e5m2`. No generic GEMV profile, compatibility
alias, or selectable characterization placement remains active.

For each domain, both schedules start with ranged element-wise MUL over its
participating mats and finish at the highest participating reachable mat:

- **MIMDRAM-InterMatFirst:** forward full-vector GB-MOV and destination ADD,
  preserving a partial destination's moved suffix, then the intra-mat
  LC-MOV/ADD tree at the sink. Preserve the characterization's physical
  arithmetic/movement order, translating placement only. This is the
  Figure-6-style GEMV adaptation; the K>2 fold remains a project composition.
- **MIMDRAM-IntraMatFirst:** apply that same local tree to each mat's valid
  products first. Full mats execute identical local stages as one range within
  this output; a partial final mat uses its own valid-count graph. Forward only
  the resulting HFF-width residual vector with singleton GB-MOV and destination
  ADD, taking destination local residuals as left operand and the incoming
  accumulator as right operand. Output rows are distinct from inputs. No
  further sink tree is required. With the accepted length constraint each
  participating mat returns exactly H residuals.

Ranged LC uses the common rows/selectors at every selected mat and copies
locally, never between those mats. Ranged operations are confined to one GEMV
output, except where the packing/fusion and GEMM rules below explicitly allow
synchronized members to share Requests.

The [canonical CUDA specification](../references/gpu-pud-gemv-programming-model.cu)
and its [summary](../references/gpu-pud-gemv-programming-model.md) supply the
arithmetic interfaces and both exact reduction graphs. GPU completion starts
at zero for each domain, adds residuals in ascending lane order, then adds the
domain sum to the output accumulator in ascending domain order. Its costs
remain outside PuD timing. That final combination is the completion boundary,
not a tail fallback. FP8 is non-associative: validate each baseline against
its own scalar execution graph, without requiring equality between baselines
or adding accuracy evaluation. Primitive, LC, GB, total Request counts,
controller cycles and peak inflight are reported under identical
placement/configuration; cycle differences are evidence, not fixed
correctness oracles.

**Length domain**

- N must be positive and divisible by HFFS_PER_MAT (H).
- N need not be divisible by MAT_SIZE (512). Partial final mats remain
  supported, including N=516.
- Arbitrary tails shorter than H are unsupported: the LC/GB movement model
  transfers whole H-position groups and has no partial-group masking or write
  semantics.
- Reject unsupported lengths explicitly. There is no partial-group movement,
  masking, padding, or host fallback.

**Temporary rows**

PuD micro-operation-level temporary rows remain private to lowered ADD/MUL
operations; their counts come from the operation generator. PuD
macro-operation-level temporary rows hold values across operations. Same-mat
micro-operations are serialized.

**Phase-latency experiment**

The standalone phase-latency experiment measures MUL and reduction within one
normal full execution, using generator layout boundary indices and opaque
PuDTrace acceptance/completion checkpoints. It rejects multi-domain inputs
because their chains interleave MUL and reduction; general GEMV
generation/execution retains multi-domain support. Physical Requests, traces,
placement, scheduling and controller timing stay unchanged. The
[user guide](../ddr4-pud-user-guide.md#gemv-trace-generation-and-execution)
defines the timestamp and output conventions.

**Legacy DDR4 GEMV placement (frozen baseline)**

The legacy DDR4 generator path uses one channel/rank and identical
deterministic BLP-first static placement for both baselines, fastest to
slowest:

```text
bank within bank group -> bank group -> legal K-mat range slot within chip
    -> chip -> subarray capacity fallback -> row-band capacity fallback
```

Every bank consumes a range slot before any bank consumes the next slot.
Select disjoint, low-to-high forward-connected ranges, checking each edge
against the profile's `gb_successor`. Leave a chip's remainder unused if it
cannot fit K; never cross a chip boundary. Each output reserves the maximum K
across its domains and each domain uses the required prefix. M=2,N=12 uses
bank0/mat0 and bank1/mat0; M=2,N=516 uses bank0/mats0..1 and bank1/mats0..1,
all in subarray0. Banks here enumerate all bank-group/bank pairs.

Keep domains sequential in one chain per output, distinct preplaced inputs,
three reused macro workspaces, protected constants and the generated maximum
ADD/MUL micro-operation temporary-row requirement. All unused rank range slots
precede reuse in a disjoint row band. The footprint is
`F = 2*w*D + 3*w + C + T`; capacity is
`banks * subarrays * chips * floor(mats_per_chip/K) * floor(rows_per_subarray/F)`.
Reject excess capacity before lowering. Subarrays and row bands provide static
capacity only. Same-bank cross-subarray execution remains serialized; SALP for
the open-bitline organization is undecided and excluded.

Preserve all 14 frozen DDR4 workloads exactly: legacy placement, trace/layout
v4 bytes, Request counts, CHAIN CSVs and cycles. Do not enable packing on the
legacy generator path or reinterpret its artifacts. Any packed DDR4
characterization uses an explicitly separate mode/artifact identity
(DDR4-packed) and must not overwrite the frozen baseline.

**Packed GEMV placement, packing, and fusion (DDR4-packed, GDDR7, HBM3)**

*Packing and synchronization.* For H <= N <= 512 with N % H == 0, use
outputs_per_mat=floor(512/N). Pack equal-N outputs into contiguous,
Group-aligned position ranges in one mat. Leave unused positions unused; add
no padding, masking, cross-position shuffle or mixed-N packing. For N>512
retain multi-mat placement, including an unused partial final mat tail; do
not place another output in that tail.

Outputs sharing physical rows execute arithmetic stages together. Complete
every member's required movement and preceding-stage suffix restoration before
executing the next shared arithmetic stage once. Preserve the non-power-of-two
prefold order: movement -> shared ADD -> suffix restoration, with every member
restored before the next arithmetic stage. Never execute one member's whole
reduction before another member sharing those rows. Each output retains its
own H residual positions and numerical result.

*Request fusion.* Maximize legal fusion within one connected path. RowCopy,
MAJ3, MAJ5, NOT and NOT_COPY may use one inclusive MatRange over contiguous
compatible mats only when ordered row operands, stage, dependencies and
physical semantics match. LC-MOV keeps distinct Group pairs as separate
Requests; one common source/destination Group pair may fuse across a
compatible contiguous range. GB-MOV remains one directed singleton mat pair;
no multi-edge primitive is introduced. Use the profile's 16/32/16-mat path as
the fusion boundary for DDR4/GDDR7/HBM3. Keep DDR4's eight chip paths separate
for GEMV even where compute/LC abstractions could span them.

*Fusion before Channel striping.* Form maximally legal fused ranges first,
then assign successive ranges round-robin to Channels: range i -> Channel
i % C. Within each Channel, advance through the fixed hierarchy order below.
Do not narrow or split a legal fused range merely to activate more Channels;
leave excess Channels idle when there are fewer ranges than Channels.
Small-workload fusion-width/Channel-utilization sensitivity is deferred. This
baseline uses all Channels whenever enough fused ranges exist; it makes no
claim of globally optimal latency.

*Packed output group and dependency ownership.* Use one physical CHAIN per
synchronized packed output group. This is software/layout grouping, not a
hardware engine, controller identity or new primitive. Do not share a physical
Request among independent CHAINs. Complete each physical Request exactly once;
multiple logical outputs may observe the same completion through metadata.
For every output retain output ID, position/Group origin, domain, sink/result
rows, residual positions and physical CHAIN/checkpoint ownership. CHAIN
remains dependency-only. Snapshot all member readouts before workspace reuse.

*Capacity and reporting.* A/x rows, products/results, workspaces, constants
and temporary rows use common physical row IDs across packed members; do not
charge a full row band per member. Use the reference's derived row/capacity
accounting and reject excess capacity early. Report useful-position
utilization, occupied mat-rows, logical outputs stored, physical Requests by
opcode, active CHAINs/controllers and PuD in-memory phase latency separately.
Request-count reduction does not establish proportional speedup.

Logical output/domain/lane identity lowers to hierarchy through Bank + Row +
inclusive MatRange + optional Group. Preserve the InterMatFirst/IntraMatFirst
arithmetic graphs, precision, x duplication, reduction semantics, sequential
domains, designated-row roles, arithmetic liveness and the operation lowerer.
Each output and packed output group remains within one Channel/Bank/subarray.

Use each target profile's H directly: DDR4 H=4, GDDR7 H=8, HBM3 H=16. Use its
connected path: respectively 16, 32 and 16 mats. DDR4 has eight x8 chips,
each contributing a separate 16-mat GB path: 128 logical mats per
Bank/subarray under one shared Channel interface. Channel aggregation
multiplies independent output placements and controller resources, never one
output's connected reduction extent or mats/Bank.

Static placement order for successive fused ranges, fastest to slowest (the
legacy DDR4 path retains its existing unfused traversal above):

| Target | Accepted order |
| --- | --- |
| DDR4-packed | Preserve the frozen DDR4 order: Bank -> BankGroup -> chip path -> subarray -> row band |
| GDDR7 | Channel -> Bank -> range slot -> subarray -> row band |
| HBM3 | Channel -> PseudoChannel -> BankGroup -> Bank -> Sid -> range slot -> subarray -> row band |

This is a deterministic fusion-first baseline with Channel striping. HBM3
BankGroup-before-Bank remains fixed. For M=2048,N=128, full-path fusion
and full Channel utilization coexist: DDR4-packed has 32 fused 16-mat ranges
on one Channel, GDDR7 has 16 fused 32-mat ranges across four Channels, and
HBM3 has 32 fused 16-mat ranges across sixteen Channels. No cross-Channel
movement, SALP, finite engine limit, padding, shuffle or arithmetic/liveness
redesign is introduced.

*Domains and latency reporting.* **D = number of domains belonging to one GEMV
output.** A domain partitions one dot product; it is not an independent
output. Capacity tables use “output capacity when D=1” or
“single-domain-per-output capacity.” Each domain leaves H PuD residual values;
report D * H residual values/output. The zero-initialized host graph's
D*(H+1) ADD calls/output remain separately reportable work. Report **PuD
in-memory phase latency**, ending at PuD residual completion including
terminal recovery. Host residual readout/folding and inter-domain
accumulation remain outside the timing model. Cross-target FP8 bit-exact
equality is not claimed because reduction grouping depends on H and
connected-path geometry. INT8 semantics remain unchanged.

*Runner refresh policy.* Preserve frozen DDR4 NoRefresh; use GDDR7 Open +
AllBank REF + zero RFM independently on each of the four x8 Channel
controllers; retain HBM3's Open + AllBank REF + zero RFM. No device-wide
refresh barrier or new staggering policy. Keep maintenance command counts,
total issued-command counts and completed PuD occurrence counts separate.
Aggregate counts across controllers without summing elapsed controller cycles.

GDDR7 and HBM3 results produced under these rules are characterization
results, not frozen performance baselines; promotion to a frozen baseline
requires user review.

**Shared-K GEMM: logical contract**

The initial shared-K GQA workload is `Q[8,128] × K[128,2048] -> O[8,2048]`.
Distinguish query index `h=0..7`, reduction index `r=0..127`, and
output/key index `j=0..2047`. Each query maps to GEMV with `M=2048`, `N=128`,
`A[j,r]=K[r,j]`, `x[r]=Q[h,r]`, and `y[j]=O[h,j]`. All queries share K; there
is no distinct K tensor per head.

Reuse the INT8, FP8-E4M3 and FP8-E5M2 GEMV MUL/ADD operations and reduction
graphs unchanged. Every MUL/ADD visible result and the final output use the
input format. Preserve INT8 low-eight-bit wrap and FP8's bounded numerical
domain and approximation/truncation behavior. Wider accumulation, FMA, new
rounding policies, and E2M1 or UINT integration are outside this scope. At
`N=128`, `H=4`, each output reduces within one MAT slice through
`128 -> 64 -> 32 -> 16 -> 8 -> 4`; both schedules therefore have the same
graph and no GB stage.

PuD completion leaves four chip-local residuals per output. The host completes
scalar O using the residual/domain fold order above. No operation to store
final scalar O in PuD is required. Measure the PuD in-memory phase starting
after all input placement and replication have completed, including terminal
recovery. Use `NoRefresh` and exclude input loading/replication, readout and
host folding time. Approximately 1 ms remains an unverified expectation, not a
correctness oracle or a reason to alter timing. Performance lower-bound
calculations and their reproduction are not GEMM deliverables.

Provide a separate GEMM API/CLI reusing the common lowering, packing/fusion
and trace/replay mechanisms. Preserve GEMV's single-vector and M/N semantics,
DDR4-packed GEMV defaults and artifact meanings, frozen legacy DDR4 GEMV, and
GDDR7/HBM3 behavior; the packed GEMV chip-local fusion policy above continues
to apply to GEMV workloads. Use a separate GEMM layout schema v1 and preserve
existing GEMV layout schemas and artifact meanings. The GEMM artifact records
Q/K/O shapes and arithmetic profile, the placement profile and hierarchy,
each output's query/key identity and physical input/result locations, and
physical group/CHAIN and checkpoint ownership. Field names and API/CLI
spellings are implementation details within that contract. Keep the
DDR4-packed/multistandard `PUD_TRACE 2` grammar and parser.

**Shared-K GEMM: placement and fusion**

GEMM builds on the DDR4-packed target. Use `DDR4_8Gb_x8` with `DDR4_2400R`:
one 64-bit Channel/rank containing eight
x8 chips, with chip h assigned to query h. Each of the 16 banks within a chip
handles 128 outputs. Place four length-128 dot products in a MAT's 512
positions, using two independent row bands in the same subarray. Each band
holds the Q/K inputs for four distinct keys per MAT, its own workspace and
residual storage. The two Q/K operands do not count as separate outputs. This
gives `16 MATs * 2 bands * 4 slices = 128 outputs` per chip-bank and
`8 * 16 * 128 = 16,384 outputs` overall. The two bands use the same MAT
resources, so their operations do not execute simultaneously. No SALP is
added.

Index-to-location enumeration:

```text
Channel = 0; Rank = 0
bank_index = j // 128
BankGroup = bank_index // 4; Bank = bank_index % 4
band = (j % 128) // 64
local_mat = (j % 64) // 4; slice = j % 4
chip = h; logical_mat = 16*h + local_mat
subarray = 0
position = 128*slice + r
Group = position // 4; HFF position = position % 4
```

At that position, the matrix operand is `K[r,j]` and the vector operand is
`Q[h,r]`. Replicate logical K across chips and Q across the output slices of
its assigned chip before measurement. The inverse output mapping is
`j = 128*bank_index + 64*band + 4*local_mat + slice`. Each output occupies a
distinct slice; neither bands nor chips extend one output's reduction domain.

Use row-band base `band*F`, where `F = 5*w + C + T`, `w=8`, C counts the union
of declared constants and T is the generated maximum ADD/MUL temporary-row
requirement. Relative row offsets are K at 0..7, Q at 8..15, primary at
16..23, reduction at 24..31, movement at 32..39, followed by protected
constants and micro-operation temporaries. Current requirements give
F=60/64/59 for INT8/E4M3/E5M2; derive these values from the operation
generator rather than hardcoding an independent allocator. Both bands fit the
subarray. After the five local ADD stages, each output's four residuals occupy
reduction rows at positions `128*slice + {0,1,2,3}` in its own MAT and band.
Preserve inputs/constants, intra-band temporary lifetimes and
primary/reduction alternation. Do not share workspaces between bands or
overwrite retained residuals during this workload.

Use exactly 16 physical CHAINs, one per Bank. Each owns 1,024 outputs across
eight chips and contains all band-0 Requests followed by all band-1 Requests.
Each band retains its 512-output group and compatible compute/LC ranges over
logical MATs 0..127. PuDTrace within-chain ordering releases the next Request
only after the preceding full callback, including terminal recovery, so band 1
cannot begin before band 0 fully completes. Different Bank CHAINs remain
independent and may overlap; there is no global barrier. CHAIN IDs remain
opaque labels, not an ordering rule.

The intermediate checkpoint is the last Request of band 0; final CHAIN
completion is band-1 completion. Retain per-output residual/readout ownership
and band membership in GEMM layout metadata. These timestamps do not describe
MUL/reduction phases. GEMV phase instrumentation is unchanged; separate
MUL/reduction latency for both GEMM bands is outside this contract. No
inter-chain predecessor configuration, general DAG scheduler or new frontend
scheduling mechanism is required.

Corresponding locations across chips hold different Q values and the same
logical K, and execute the same operation sequence. For GEMM, compute with
matching Bank/subarray, row bindings, dependency frontier and destructive
semantics may fuse over compatible contiguous cross-chip MatRanges. LC may
likewise fuse copies within each MAT for one common Group pair. Different
slice-specific Group pairs remain separate Requests; complete all required
movement before shared arithmetic. Preserve the packed group's single
physical CHAIN ownership and exactly-once completion contract, with per-output
query/key identity, residual locations and checkpoints.

Cross-chip compute/LC fusion does not enlarge the connected reduction domain
or GB topology. GB remains chip-local and directed with singleton endpoints.
Bank-addressed Requests contend for the shared command bus while exploiting
bank overlap. Simultaneous multi-bank broadcast is not required, and no new
command or timing behavior is assumed. Apply this policy only through the
separate GEMM interface.

Rationale

At 512 represented elements per mat, a 2048-element vector spans four
mat-local fragments; larger vectors need an explicit rule for merging
contributions across mats. The forward fold supplies that rule using only
accepted movement units. Direct generation lets the project choose reachable
placement and schedules without inventing the unspecified parts of generic
MIMDRAM movement lowering. Keeping disconnected domains separate preserves the
host-completion boundary. Separating the published ranged interface from the
supported singleton unit avoids presenting a conservative model as the
complete ISA.

Two named baselines maintain one unambiguous source of truth for evaluation
without silently retaining a third GEMV policy. Bank striping exposes BLP
before additional same-bank mat placement. Comparing the Figure-6-style
inter-mat-first order with local-first reduction isolates the reduction
schedule while preserving placement, supported operations and completion
boundaries. Ranged LC authority permits identical local stages within one
output without a movement-model extension.

Whole-group alignment preserves the specified graph with existing movement
and full-mat-row compute. For N=516, the final mat has four valid local
products; its moved suffix starts at a group boundary and can be restored
without overwriting those four results. Irregular lengths such as N=12 also
have aligned prepass moves. Unconsumed physical columns are outside the
logical result, not extra zero-valued GEMV terms. The counterexamples explain
the unsupported domain: N=3 requires column 2 to column 0, changing HFF
position; N=7 and N=513 require preservation copies splitting a group
containing new ADD results. Rounding such copies would overwrite live results.
Additional temporary rows alone supply neither cross-position movement nor
partial writes. Padding or changing the FP8 graph is not an equivalent repair
under the arithmetic contract. This is a project macro-domain choice, not a
MIMDRAM or PRADA source fact; the broader arbitrary-tail alternative is not
accepted.

GEMM adds per-query input identity without changing the arithmetic graphs. A
separate interface makes shapes and result identities explicit while reusing
the operation lowerer and physical execution contract. Two independent row
bands allow all inputs to be preplaced while preserving the first band's
residuals. Cross-chip fusion uses existing compute/LC range support to express
the shared-K workload without adding GB connections or multi-bank commands.
One CHAIN per Bank enforces the required band ordering and bank concurrency
using existing execution and fits the current checkpoint interface; the
trade-off is excluding separate MUL/reduction timing for both bands.

Evidence

- **Provenance.** Consolidated on 2026-11-19. The now-Superseded
  [reduction placement and movement-lowering decision](superseded/mimdram-reduction-placement-and-movement-lowering.md)
  (accepted 2026-09-09) and [GEMV macro contract](superseded/pud-gemv-macro-contract.md)
  (baselines accepted 2026-09-14, phase-latency experiment 2026-09-15, GEMM
  contract 2026-10-11) retain their acceptance-time text. The packed GEMV
  placement (G7, accepted 2026-09-17 and re-accepted with packing/fusion) and
  GEMM placement/fusion (accepted 2026-10-11; the earlier 32-CHAIN contract
  and D1 frontend predecessor extension were replaced by the 16-CHAIN
  contract before implementation) moved here from the
  [multistandard decision](pud-multistandard-substrate.md); their
  acceptance-time text is in Git history at `e0146f2`. The former same-bank
  GEMV placement is in its [Superseded decision](superseded/pud-gemv-output-placement.md).
- **Source facts.** The
  [MIMDRAM movement reference](../references/mimdram-inter-column-data-movement.md),
  §§1.3, 1.5, 1.6, and 4, records the instruction/interface, directed
  neighboring datapath, two-mat reduction example, precision dependence, and
  lowering gaps; the [mapping/reduction reference](../references/mimdram-data-mapping-and-vector-reduction.md)
  records physical movement granularity and source limits. Neither these nor
  the [geometry reference](../references/mimdram-geometry.md) establishes
  vendor physical numbering or the K-mat fold.
- **Investigation.** The
  [Phase-4 investigation](../references/investigations/pud-phase4-g5-g7-investigation.md),
  especially §5 and §11, retains packed placement derivations, capacities,
  primitive legality, arithmetic proofs and alternatives.
- **Implementation.** The [GEMV generator](../../../tools/pud_gemv_generator/generator.py)
  (`_group_placement`, `_fuse_group`), [arithmetic requirements](../../../tools/pud_operation_generator/requirements.py),
  and [functional replay](../../../tools/pud_gemv_generator/validation.py)
  implement the graphs, placement and fusion.
  [Location authority](../../../src/ramulator/dram/pud_location.cpp) and
  [request validation](../../../src/ramulator/controller/pud_request_validation.cpp)
  retain profile-defined directed neighbors, singleton GB endpoints, and
  cross-chip compute/LC ranges within a common Bank/subarray context.
  [PuDTrace](../../../src/ramulator/frontend/impl/memory_trace/pud_trace.cpp)
  readies every nonempty CHAIN and advances only within-chain successors on
  callback; it has no inter-chain dependency configuration, repeated CHAIN
  selection appends to the same chain, and numeric IDs or first-appearance
  order do not establish predecessor completion ordering; [controller completion](../../../src/ramulator/controller/controller_base.cpp)
  releases terminal-recovery protection before the callback.
- **Validation.** [GEMV baselines](../plans/completed/pud-gemv-baselines-plan.md),
  [trace integration](../plans/completed/pud-gemv-trace-integration-plan.md),
  [multistandard Phase 4](../plans/completed/pud-multistandard-substrate-plan.md#phase-4--reusable-operationgemv-integration-and-characterization),
  and [GEMM](../plans/completed/pud-gemm-plan.md#completion-evidence--2026-10-11)
  record implementation and validation, including exact preservation of the
  14 frozen DDR4 workloads. GEMM was committed in `80f4b6d`.

Open issues

- Full target-size GEMM latency remains unmeasured; approximately 1 ms is an
  unverified expectation. GEMM generalization beyond the initial shape is not
  decided.
- GDDR7/HBM3 characterization results await review before any promotion to a
  frozen baseline.
- Small-workload fusion-width/Channel-utilization sensitivity is deferred.
- Arbitrary tails, partial-group movement, and other movement capabilities
  require separate future authority.
- The movement-reference gaps remain: multi-mat GB pairing and simultaneous
  execution, overlapping ranges, non-neighbor/forward multi-hop lowering and
  temporary-row interaction, reverse and cross-chip routing, and the exact
  lowering algorithm for those cases. Generic `bbop_mov` routing or additional
  placement/topology would require a later decision.
- UINT4/INT4, FP4-E2M1, and other formats are covered by single-operation
  lowering but are not GEMV/GEMM profiles; 4-bit packing, placement and
  integration remain separate decisions.
