# GDDR7 PuD modeling reference

Investigation date: 2026-09-16. Source checkout:
`b8081b2f7c9e4f6c9e010cc09d7577700a234e2e`; working tree clean at entry.
Scope: GDDR7 G1/G2/G3/G4/G6 and the common finite-control-engine
abstraction audit, including public MIMDRAM and Proteus artifacts. The initial
investigation started from a clean tree; this follow-up retains the preceding
documentation edits.
This reference contains evidence,
calculations, modeling alternatives and their limitations; it selects no policy.
The [canonical decision](../decisions/pud-multistandard-substrate.md) owns
Accepted, Proposed and Open items; see it for G1/G2/G3/G4/G6 and the common
finite-engine scope amendment. G6 policy acceptance does not repair production
timing definitions; the existing-model gaps below remain implementation work.
This reference does not reopen Accepted choices.
No production code or tests were changed.

## 1. Evidence and verification boundary

### Supplied physical-organization claims

- **Verified representative geometry:** Chatterjee et al., NVIDIA/UT Austin,
  [*Architecting an Energy-Efficient DRAM System For GPUs*, HPCA 2017](https://research.nvidia.com/sites/default/files/pubs/2017-02_Architecting-an-Energy-Efficient/chatterjee.hpca2017.pdf),
  §III, PDF pp. 2–3 and Fig. 3, describes 512×512-cell mats, 32 horizontally
  grouped mats activated together, a 2-KB subarray row buffer, and eight bits
  per mat in a 32-byte DRAM atom. The discussion concerns contemporary
  GDDR5/HBM; Fig. 3 depicts one HBM channel. It also describes HFFs on the
  local/master-data-line connections. This is representative physical
  organization evidence, not a GDDR7 characterization or a MIMDRAM port.
- **GDDR7 2-KB page:** supplied by the user; independently consistent with the
  repository's `2048 columns × 8 DQ = 16384 bits`. No GDDR7 specification or
  vendor page-size table was available in the repository, and the targeted
  public-source check did not establish that table. The supplied hardware claim
  and verified modeled page size are distinct evidence.
  Here KB means 1024 bytes, so the candidate page is 2 KiB.
- **Channel/package cross-check:** Micron's
  [GDDR7 product brief, Table 1](https://www.micron.com/content/dam/micron/global/public/products/product-flyer/gddr7-product-brief.pdf)
  lists a 32-bit device, four channels/package and 32-byte access/channel.
  This supports interpreting the repository instance as one x8 channel slice;
  it does not supply internal mat placement.
- **GPUHammer address granularity:** the user supplies evidence that real GPU
  DRAM bank/row mapping has 256-B granularity. This is recorded as supplied
  realistic-address-mapping evidence, not an independently checked GDDR7
  part-specific result. No exact bank hash/XOR functions or equivalence to
  Ramulator channel interleaving were supplied. It does not determine a
  `CacheLineInterleave` setting or replace explicit PuD placement.
- **HBM3, deferred:** the user supplies two pages per Channel, each 1 KB.
  This is retained as a source claim for the HBM3 milestone, not independently
  verified here. `1024×8/512 = 16` mats per page is a **derived hypothesis**
  only if one page spans one complete row of such mats. Page/PseudoChannel/
  subarray/Sid relationships and burst participation remain unverified for that
  milestone. This arithmetic alone establishes neither 16 mats/subarray nor
  applicability of the GDDR7 profile.

### Existing project references and authority

Existing technical material includes the
[DDR4 PRADA derivation](ddr4-pud-timing-reference.md),
[primitive definitions](pud-primitives.md), [MIMDRAM geometry](mimdram-geometry.md),
[LC/GB technical reference](mimdram-inter-column-data-movement.md), and
[mapping/reduction reference](mimdram-data-mapping-and-vector-reduction.md).
These documents supply the existing circuit/mechanism evidence.
OC means **Offset Cancellation**.

The [multistandard decision](../decisions/pud-multistandard-substrate.md)
records project policy separately from this reference. Existing [placement](../decisions/mimdram-addressing-geometry-and-payload.md),
[execution](../decisions/mimdram-movement-execution-ownership-and-device.md),
and [timing/resources](../decisions/mimdram-movement-timing-and-resource-model.md)
separate source mechanisms from the accepted DDR4 hybrid and common footprint
policy. Their DDR4 numbers are not GDDR7 calibration.

### Source and test inspection

The primary sources for simulator claims are:

- [GDDR7 Python specification](../../../python/ramulator/dram/gddr7.py) and
  [generated registration](../../../src/ramulator/dram/impl/GDDR7.cpp);
- [config conversion](../../../python/ramulator/dram/spec.py),
  [transaction sizing](../../../src/ramulator/dram/dram_spec.h),
  [mapper compaction](../../../src/ramulator/controller/addr_mapper/addr_mapper_base.cpp),
  [RoBaRaCoCh](../../../src/ramulator/controller/addr_mapper/impl/ro_ba_ra_co_ch.cpp),
  and [channel routing](../../../src/ramulator/memory_system/channel_mapper/impl/cache_line_interleave.cpp);
- [GDDR7 controller](../../../src/ramulator/controller/impl/gddr7_controller.cpp),
  [shared dual-bus scheduling](../../../src/ramulator/controller/impl/hbm_controller_base.cpp),
  [Device](../../../src/ramulator/dram/device.cpp), and the current
  [DDR4-only binding](../../../src/ramulator/dram/pud_binding_ddr4.cpp);
- [Device tests](../../../tests/device_timings/test_gddr7.py),
  [controller tests](../../../tests/controller_scheduling/test_gddr7.py),
  [smoke configuration](../../../tests/smoke/testcases/gddr7.py), and
  [latency/throughput configuration](../../../tests/latency_throughput/testcases/gddr7.py).

Read-only local Python serialization confirmed organization, timings and
command occupancy. Existing Device-harness probes reproduced the PREab gaps
in §6. Imports came from this checkout with `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONPATH=python:.`, `LD_LIBRARY_PATH=.`, and
`ramulator2-venv/bin/python3`. These are focused observations using the
existing build, not a rebuild, full regression run or physical validation.

## 2. G1 — placement consistency and determinism

### What one modeled Channel represents

The node path is `Channel -> Bank`, with Row and Column address coordinates;
there is no Rank, BankGroup, package or Chip node. Each Device/controller has
one Channel and 16 Banks. DQ and channel width are both eight bits, hence
the parallel-width factor is one. Prefetch is 32 and transaction size is
`32×8/8 = 32 bytes`, not 64 bytes; a test frontend's 64-byte stream stride
does not change that transaction size.

The controller configuration test composes four separate instances to model
a full device. A single instance does not automatically instantiate four
channels or multiple chips/packages. The modeled participation width is one
x8 **channel slice**. A profile field named Chip would not, by that name alone,
establish a whole-package mapping or replicated packages.

| Organization preset | Rows/Bank | Modeled capacity/Channel | Candidate 512-row subdivisions/Bank |
| --- | ---: | ---: | ---: |
| GDDR7_16Gb_x8 | 16384 | 512 MiB (4 Gibit) | 32 |
| GDDR7_32Gb_x8 | 32768 | 1 GiB (8 Gibit) | 64 |
| GDDR7_64Gb_x8 | 65536 | 2 GiB (16 Gibit) | 128 |

The preset names are not per-instance capacities. Density fields are
4096/8192/16384 Mb; the dimensions give the capacities above without needing
an invented package multiplier. Arithmetic consistency does not establish
physical PuD placement for any of the three presets.

### Geometry and transfer-width derivation

Given 512 rows/mat, 512 cells/mat-row, 32 mats/subarray and 512 rows/subarray:

```text
organization_columns * dq       = 2048 * 8  = 16384 bits = 2 KiB
mats_per_subarray * cells/row    =   32 * 512 = 16384 bits = 2 KiB
dq * prefetch                   =    8 * 32 =   256 bits = 32 B
organization_columns / prefetch = 2048 / 32 =    64 bursts/page

H = hff_equivalent_positions_per_mat
  = dq * prefetch / mats_per_subarray
  = 8 * 32 / 32 = 8

cells_per_mat_row / H = 512 / 8 = 64 groups/mat-row
32 * 8 = 256 bits/burst; 64 * 256 = 16384 bits/page
32 * 512 * 512 = 8388608 bits = 1 MiB/candidate subarray
16 banks * 32 subarrays/bank * 1 MiB = 512 MiB/first-preset channel
```

**The candidate is internally consistent.** Under the existing exhaustive,
equal-width, all-mats-per-burst contract, H is forced to eight. NVIDIA's
representative eight-bit mat contribution is corroborating transfer evidence;
it is **not direct evidence for eight MIMDRAM HFFs in GDDR7**. Using H=8 for
LC/GB position correspondence is a project-derived HFF-equivalent model.
Different burst participation or grouping would require a different contract.

### What the evidence does not determine

The supplied geometry fixes candidate dimension counts, conditional on its
application to GDDR7. It does not uniquely determine:

- whether a particular GDDR7 device actually uses those mats/subarrays;
- which external row IDs share a physical subarray;
- DQ/beat/byte-bit to mat, local column and ordered transfer-position mapping;
- logical-mat order, physical contiguity, or the directed neighboring GB path;
- GDDR7 realization of mat-selective activation/close and the PRADA/MIMDRAM
  hybrid, including HFF retention across LC source PRE.

The current DDR4 PuD integration uses `CacheLineInterleave + RoBaRaCoCh`:
see the [binding](../../../src/ramulator/dram/pud_binding_ddr4.cpp),
[resolver checks](../../../src/ramulator/dram/pud_location_ddr4.cpp), and
[example configuration](../../../examples/ddr4_pud_microbenchmark_config.py).
The channel mapper selects bits above the transaction offset, plus its
`interleave_bits`; RoBaRaCoCh decodes the intra-channel address separately.
GDDR7's 32-B transaction and GPUHammer's supplied 256-B bank/row granularity
are different quantities. Neither establishes a 256-B channel stripe or
GPU bank hash/XOR. No such mapper equivalence has been verified.

The [PuD trace](../../../src/ramulator/frontend/impl/memory_trace/pud_trace.cpp)
and resolved Request path use explicit hierarchy/Row/MatRange/optional Group
placement; they do not need a scalar physical byte address per operand.
The G1 decision keeps that placement authoritative and labels ordinary PA
mapping provisional. A scalar byte-to-cell map is a separate compatibility
interpretation, not physical GDDR7 wiring evidence.

For example, the following is an **illustrative invertible compatibility map**:
one Channel, `CacheLineInterleave` plus `RoBaRaCoCh`, no remapping or reserved
offset, one x8 slice, ascending mat order, contiguous 512-row subdivisions,
and consecutive eight-cell groups. For a byte address A in the first preset
and bit b in 0..7:

```text
o = A % 32; B = (A / 32) % 64
Bank = (A / 2048) % 16; Row = A / 32768
Subarray = Row / 512; LocalRow = Row % 512
Mat = o; h = b; Group = B; CellColumn = 8*Group + h
A = Mat + 32*(CellColumn / 8) + 2048*Bank
    + 32768*(512*Subarray + LocalRow)
b = CellColumn % 8
```

All divisions are integer; this example's domain is `0 <= A < 512 MiB`
with valid coordinates.
This map is algebraically invertible. Permuting mat or group order gives
other valid maps with identical dimensions, demonstrating non-uniqueness.
Choosing directed GB neighbors `m -> m+1`, m=0..30, is a further modeled
topology convention; no wraparound or cross-channel path follows from it.
Neither that topology nor the scalar map was installed or execution-tested.

**Evidence boundary:** a hypothetical modeled profile can specify dimensions
and mapping/topology conventions without further physical characterization.
A claim of verified GDDR7 physical placement instead depends on a
part-specific organization/array description, page-size/addressing table,
internal row/column mapping, and compatible mat-selective/transfer datapath.
The 2017 source does not establish those claims. The complete placement
profile is therefore **not deterministic from the supplied evidence alone**.

H=8 would imply eight bits/singleton movement and eight residual positions
for the existing position-preserving reduction mechanism, not a new shuffle
or scalarization. G5/G7 and 512-row arithmetic capacity validation remain
later gates; this investigation chooses no trace or GEMV policy.

## 3. G2 — PRADA timing policies

### Reconstruct the accepted DDR4 derivation

The [timing reference](ddr4-pud-timing-reference.md) records PRADA's
`tOC=5 ns`, `tN=35 ns`, and temporal NOT `81.32 ns`. The project uses
`tCS=4 ns`, supported by the waveform and the derived RowCopy difference
`131.64−81.32=50.32 ns`. DDR4_2400R supplies `tRP=16×0.833=13.328 ns`.

```text
T_ACT_P = 81.32 - 35 = 46.32 ns
tSR = 46.32 - 5 - 4 - 13.328 = 23.992 ns
(A*, A, A_S*, A_S, N) = (9, 4, 32.992, 27.992, 35) ns
DDR4 ceil(phase / 0.833) = (11, 5, 40, 34, 43) CK
```

tSR is a calibrated residual, not a separately measured PRADA quantity.
Retaining all physical phases and retaining the aggregate calibration when
PRE changes are different policies.

### Independent quantization and alternative calibrations

The calculations use the current project GDDR7 evaluation baseline timing
preset, `GDDR7_28000_PAM3`: one CK4 tick = 571 ps =
0.571 ns, `nRP=30`, hence target recovery `tRP=17.130 ns`. Each independently
enforced phase is calculated with `Q(t)=ceil(t/0.571)`; nRP is the preset value.

| Policy | Physical assumptions/derivation | Phase ticks (A*, A, A_S*, A_S, N); PRE | Trade-off |
| --- | --- | --- | --- |
| A: retain physical phase times | Retains the DDR4-derived tSR=23.992 ns as well as tOC/tCS/tN; substitutes only target PRE recovery. | (16, 8, 58, 50, 62); 30 | Transparent portability hypothesis; GDDR7 temporal NOT becomes 85.122 ns continuously, not 81.32 ns. No target circuit calibration. |
| B: retain tOC/tCS/tN and aggregate calibration | tSR=46.32−5−4−17.130=20.190 ns; A_S*=29.190 ns, A_S=24.190 ns. | (16, 8, 52, 43, 62); 30 | Keeps continuous NOT=81.32 ns and RowCopy=50.32 ns by making sensing faster when PRE becomes slower. This compensation is a project assumption, not GDDR7 evidence. The residual depends on selected recovery; a nonpositive residual would invalidate this decomposition. |
| C: require GDDR7 circuit calibration | Requires target tOC_C/tCS_C/tSR_C/tN_C with defined anchors and operating conditions. | (Q(tOC_C+tCS_C), Q(tCS_C), Q(tOC_C+tCS_C+tSR_C), Q(tCS_C+tSR_C), Q(tN_C)); 30 only if the same baseline recovery is selected | Stronger physical basis, but required calibration is unavailable. There is no justified numeric C tuple yet. |

For C, a conversion-only example can be calculated **conditionally**: if
future calibration returned exactly `(5,4,23.992,35) ns`, Q would return
`(16,8,58,50,62)`. This reuses A's input solely to illustrate quantization;
it is not a fabricated GDDR7 calibration or evidence that C equals A.

With no extra ACT overhead or contention, sums from first ACT **reception**
through terminal recovery are:

| Primitive | A ticks (ns) | B ticks (ns) |
| --- | ---: | ---: |
| RowCopy, one destination | 96 (54.816) | 90 (51.390) |
| MAJ3 | 104 (59.384) | 97 (55.387) |
| MAJ5 | 120 (68.520) | 113 (64.523) |
| NOT | 150 (85.650) | 144 (82.224) |
| NOT_COPY | 158 (90.218) | 152 (86.792) |

These are candidate arithmetic totals, not executable GDDR7 PuD results.
MIMDRAM's reported <0.5% fine-grained ACT-latency increase is source evidence
from its evaluated implementation, as recorded in the
[technical reference](mimdram-inter-column-data-movement.md#12-fine-grained-mat-access-structures).
It is not a measurement of the proposed GDDR7 PRADA+MIMDRAM hybrid.
All GDDR7 calculations here use unscaled phase times; the
[Accepted GDDR7 overhead exclusion](../decisions/pud-multistandard-substrate.md#accepted-gddr7-act-overhead-exclusion-2026-09-16)
owns the no-envelope/no-sensitivity policy. Under Policy A the candidate
tuple is `(16,8,58,50,62)` CK4. The canonical decision now selects A;
B/C remain analytical comparisons, not pending alternatives to that acceptance.

### Reception, physical phase and completion anchors

The current serializer treats declared timing edges as finish-reception to
finish-reception intervals, while commands are timestamped at their first
issue tick. With occupancy c, the last reception tick is `R=I+c−1`:

```text
I_follow - I_pre >= nominal_phase_ticks + c_pre - c_follow
terminal_recovery_deadline = I_PRE + c_PRE - 1 + nRP
```

The issue-gap conversion is verified repository behavior; the recovery formula
is the completion anchor selected in G2. Neither proves a PuD command encoding.
Current conventional ACT and RD/WR take two CK4; PRE takes one. Accordingly,
ACT→PRE nRAS=60 becomes a 61-tick first-issue gap; PRE→ACT nRP=30 becomes
29, since ACT reception completes a tick after issue. Bus occupancy is a
separate first-issue readiness check. GDDR7 has no HBM34
rising/falling half-tick pairing rule.

With G2's final-reception anchors and G3's selected assignment of
two-tick ACT-like commands and a one-tick close/N, A_S*→N under Policy A
has a first-issue gap of `58+2−1=59` ticks. This is reception-adjusted issue
spacing, not a different A_S* phase duration; that duration remains 58 CK4.
With that convention, first-ACT-issue to completion is one tick longer than the table's
first-reception totals. PRE's one-tick reception leaves terminal completion
at `I_PRE+30`. The ordinary 29-tick PRE→ACT issue gap is distinct from
PuD ownership lifetime; protection in this alternative lasts through `I_PRE+30`.

Invocation-local Device edges currently consume serialized values, whereas
the DDR4 occurrence-specific movement binding reads raw timing values.
Under G2's reception-anchor policy, translating the latter once gives
consistent offsets; copying raw delays or adjusting twice would make the two
paths disagree.
No DDR4 anchor or global clock implementation is changed here.

Policy A preserves the assumed individual physical phase times while changing
the aggregate through target PRE recovery. Policy B preserves the aggregate
by changing the sensing residual. Policy C depends on new GDDR7-compatible
PRADA/hybrid circuit calibration. The available evidence does not select
between those experimental invariants or establish target circuit accuracy.

## 4. G3 — hierarchy and resource evidence

### Verified command-bus semantics

The [GDDR7 controller](../../../src/ramulator/controller/impl/gddr7_controller.cpp)
has **one row-command issue path and one column-command issue path**.
Each simulator tick attempts an internal RCK command, otherwise a normal
column command, then a row command. One ready row command and one ready
column command may issue at the **same simulator timestamp**. It inherits
HBMControllerBase scheduling, not HBM34's half-tick edge/pairing rules.

A command with occupancy **2 CK4 occupies its own command bus for two
simulator ticks**. A start at T prevents another start on that bus at T+1;
the other bus has its own occupancy and timing checks. The generated bus
edges are Channel-scoped. This does **not** mean four commands may issue per
memory-controller cycle: the implemented tick has at most one issue on each
of two paths. CK4 is a timing/reference-clock term, not a command-count
multiplier. Frontend/controller clock ratios do not add issue paths.

| Current conventional commands | Modeled command bus | Occupancy |
| --- | --- | ---: |
| ACT | Channel row bus | 2 CK4 |
| RD, WR, RDA, WRA | Channel column bus | 2 CK4 |
| RCKSTRT, RCKSTOP | Channel column bus | 2 CK4 |
| PREpb, PREab, REFab, REFpb, RFMab, RFMpb | Channel row bus | 1 CK4 |

The source currently defines no GDDR7 PuD command encoding, bus assignment
or engine pool. GenericDDR's E=8 default is not a GDDR7 hardware resource fact.
The selected command-resource/RCK terms are in the decision. The finite-engine
evidence below distinguishes current implementation from that common policy.

### Compute-engine count, lifetime and pool scope

**Current implementation facts, not the newly Accepted execution model.**
Production code is unchanged. The audit below explains why its eight-Request
limit cannot be attributed to MIMDRAM; the common decision supersedes that
performance constraint without introducing a replacement bbop engine model.

The [allocator](../../../src/ramulator/controller/pud_execution.cpp)
(`allocate_pud_compute`) scans pending compute Requests oldest-first and finds
a free engine ID in `[0,E)`. The
[controller lifecycle](../../../src/ramulator/controller/controller_base.cpp)
(`reserve_pud_compute`, `retire_request`, `release_completed_resources`) commits
one protected record containing that engine and the entire Request footprint,
then releases it only at delayed departure after terminal recovery.

| Question | Verified implementation answer |
| --- | --- |
| What is E=8? | The configurable `pud_compute_engines` default in GenericDDR: eight allocation slots per pool, not mats, Banks, queue entries or command issues/tick. |
| One engine per active compute primitive Request? | Yes, from successful allocation before its first ACT; merely queued/unallocated Requests own none. |
| Retained through terminal recovery? | Yes, including pre-ACT waits, execution and terminal PRE+nRP recovery; not released at terminal issue. |
| Multiple mats in one Request? | Still one engine for its full mat range, not one engine/mat. |
| LC-MOV / GB-MOV? | No compute engine: movement records use engine=-1 and retain footprint/recovery protection. |
| Maximum concurrent compute Requests in one E=8 pool? | At most eight allocated primitives, counting pre-ACT and recovery; timing/conflicts can reduce executing concurrency. |
| Sixteen-Bank compute BLP consequence? | With each primitive targeting one Bank, at most eight Banks can simultaneously hold compute primitives in this pool. Multiple disjoint primitives in one Bank can reduce the distinct-Bank count further. This does not cap ordinary traffic or engine-free movement at eight Banks. |
| Current DDR4 behavior? | Yes. `DDR4PuDBinding::engine_pool` selects Channel, sharing the pool across all its Ranks/Banks. There is no per-Bank multiplication of E. |

The existing [allocation tests](../../../tests/controller_scheduling/GenericDDRController/test_pud_allocation.py)
exercise E=1/2/8 across Banks and Ranks through recovery; the
[lifecycle tests](../../../tests/controller_scheduling/GenericDDRController/test_pud_protected_lifecycle.py)
cover pre-ACT ownership, multi-mat Requests and recovery release.

### Operation-context audit

#### Paper architecture, area and performance evidence

- [SIMDRAM](https://ghose.web.illinois.edu/papers/21asplos_simdram.pdf),
  §4.3/Fig. 7, executes queued bbops one at a time, with a loop over row-sized
  array batches. §5.2/Table 1 specifies arrays, element count `size` and
  precision `n`. Separately, §6 evaluates 1/4/16 Banks and states same-Channel
  Banks operate in parallel without further modifications. This reports BLP;
  it does not specify a multi-Bank bbop control mechanism sufficient to derive
  this project's primitive admission, partition scheduling or release rules.
- [MIMDRAM](https://ghose.web.illinois.edu/papers/24hpca_mimdram.pdf),
  §4.2/Fig. 7, allocates a free microProgram engine to a bbop and describes
  concurrent operations limited by those contexts. On completion it frees
  scoreboard mats and notifies the CPU. Table 2 reports eight engines in the
  controller-resident control unit; §8.5 separately estimates their area.
  §6.1/Table 1 includes `bbop_mov`, translated to LC/GB. §8.4/Fig. 14 separately
  evaluates BLP/SALP through 16 Banks and 64 subarrays/Bank. These facts do
  not establish eight engines per Bank or one engine per physical primitive.

**Abstraction mismatch:** a paper bbop/microProgram context is not the project's
physical RowCopy/MAJ/NOT Request. The current implementation's compute-only
slot accounting, with LC/GB uncharged, is a project artifact, not a
source-established MIMDRAM engine model.

**Unresolved prior-work connection:** finite control machinery and evaluated
BLP/SALP are insufficiently connected to derive a faithful finite-engine runtime
model here. Neither arbitrary multi-Bank fan-out under one engine, replication
of E per Bank, Figure 14 using E×Banks, nor a primitive-level E=8 bottleneck
follows from the cited descriptions. LC/GB locality/topology restrictions
further prevent inferring generic multi-Bank control from movement. The earlier
claim that one bbop necessarily explains all multi-Bank parallelism was an
unsupported inference, not a paper fact. No claim is made that unpublished
evaluations definitely replicated or ignored engines.

#### Public MIMDRAM simulator inspection

Inspected on 2026-09-16 at revision
`23495f10950d891a95a0b8a05d0a6a88e92de154` of
[CMU-SAFARI/MIMDRAM](https://github.com/CMU-SAFARI/MIMDRAM/tree/23495f10950d891a95a0b8a05d0a6a88e92de154).
Read-only source inspection covered the workload expansion, x86 decoder/
row-operation microops, Request payload, DRAM controller/header/configuration
and repository searches for bbop, microProgram and engine-allocation state.
This was not a simulator build or reproduction of paper figures.

| Public path | Observed mechanism |
| --- | --- |
| [Workload macros](https://github.com/CMU-SAFARI/MIMDRAM/blob/23495f10950d891a95a0b8a05d0a6a88e92de154/microworkloads/mimdram.h) and [addition example](https://github.com/CMU-SAFARI/MIMDRAM/blob/23495f10950d891a95a0b8a05d0a6a88e92de154/microworkloads/00_addition-plus.c) | C loops expand AP/AAP vector work into row-operation calls; vector width uses Bank/Rank constants. This is software expansion, not evidence of a hardware engine controlling arbitrary Bank partitions. |
| [x86 row operations](https://github.com/CMU-SAFARI/MIMDRAM/blob/23495f10950d891a95a0b8a05d0a6a88e92de154/gem5/src/arch/x86/isa/microops/rowbit.isa) and [Request](https://github.com/CMU-SAFARI/MIMDRAM/blob/23495f10950d891a95a0b8a05d0a6a88e92de154/gem5/src/mem/request.hh) | RowOp payload carries opcode and source/destination addresses; exposed operations include AND/OR/NOT/XOR/AP/AAP. No paper-level bbop interpreter or microProgram-engine allocator was found in this path. |
| [DRAM controller](https://github.com/CMU-SAFARI/MIMDRAM/blob/23495f10950d891a95a0b8a05d0a6a88e92de154/gem5/src/mem/dram_ctrl.cc), `addToWriteQueue`, `doDRAMAccess`, `processNextReqEvent` | Row operations enter the write queue; `pendingRowOps` requests write draining. Fixed AP/AAP sequences update Bank timing and completion/bus state. The counter is decremented on servicing a row operation; it is not an E-sized resident-engine pool. Ordinary queue/timing constraints still exist. |

**Bounded implementation finding:** the public framework inspected here does
not implement observable finite microProgram-engine occupancy/backpressure.
No matching bbop-engine allocation, E-sized occupancy, engine release or
finite-engine concurrency enforcement was found. Existing row-operation
execution is not a complete implementation of the paper's control-unit model.
The public code establishes only its own modeled mechanisms; it cannot prove
how every unpublished simulator/configuration behind MIMDRAM's figures behaved.
Paper architecture and area accounting remain separate evidence.

#### Public Proteus analytical model inspection

Inspected on 2026-09-16 at revision
`30abc72d9156c4ede8137c8c60ae3fb3f87dc9e2` of
[CMU-SAFARI/Proteus](https://github.com/CMU-SAFARI/Proteus/tree/30abc72d9156c4ede8137c8c60ae3fb3f87dc9e2).
Its [README](https://github.com/CMU-SAFARI/Proteus/blob/30abc72d9156c4ede8137c8c60ae3fb3f87dc9e2/README.md)
describes instrumented applications using analytical costs driven by prior
SIMDRAM/MIMDRAM gem5 work. That provenance does not reveal the missing
control-capacity semantics of the underlying cost-generation runs.

In [`util/bbop_manager.c`](https://github.com/CMU-SAFARI/Proteus/blob/30abc72d9156c4ede8137c8c60ae3fb3f87dc9e2/util/bbop_manager.c),
`get_simdram_adder_latency` selects tabulated costs by precision and multiplies
by a size-dependent repetition factor, using one or 64 subarrays' SIMD width.
Multiplier/ReLU and Proteus cost paths likewise use operation/precision,
array parallelism and, where selected, tFAW-related restrictions.
`bbop_op` accumulates these analytical costs by bbop ID; it does not run
a finite SIMDRAM/MIMDRAM engine-admission/release scheduler.
The [header](https://github.com/CMU-SAFARI/Proteus/blob/30abc72d9156c4ede8137c8c60ae3fb3f87dc9e2/util/bbop_manager.h)
sets `SIMD_WIDTH=65536`, `SUBARRAYS=64` and `MAX_BBOPS=100`.
The last sizes statistics indexed by bbop ID; it is not 100 concurrent engines.
Host OpenMP thread count is likewise not a modeled PuD control-engine count.

**Bounded implementation finding:** these public analytical performance paths
contain no explicit finite SIMDRAM/MIMDRAM control-engine occupancy,
backpressure or release constraint. This is a fact about the public Proteus
model, not proof that every prior unpublished evaluation omitted that limit
or that precomputed costs contain no other overhead.

#### Current project boundaries and where they are lost

| Construct | Source-verified role / bbop relationship |
| --- | --- |
| GEMV macro | The [programming specification](gpu-pud-gemv-programming-model.cu) and [Accepted macro contract](../decisions/pud-gemv-macro-contract.md) compose MUL, movement and ADD stages, plus GPU residual/domain combination. A whole GEMV or output chain is not one existing ADD/MUL microProgram. |
| ADD/MUL invocation | One typed `pud_vector_*` call has array pointers, element count and mat range. In [generator.py](../../../tools/pud_gemv_generator/generator.py), one `arithmetic(...)` call instantiates one selected ADD/MUL program over an output's placed range. This resembles an operation-level boundary, not a source-defined runtime engine allocation. |
| Logical move | One `pud_mov` call specifies elements/precision. The generator's `move(...)` expands its corresponding movement step over bits and HFF groups into one or many LC/GB Requests, including existing within-output ranged LC. Those transfers are children of the logical move, not separate ISA bbops. |
| Physical primitive Request | RowCopy/MAJ3/MAJ5/NOT/NOT_COPY or LC/GB is a lower-level invocation with command occurrences. [Validation](../../../src/ramulator/controller/pud_request_validation.cpp) requires its operands to share Bank/subarray; it is not an array-wide bbop. |
| CHAIN | [PuDTrace](../../../src/ramulator/frontend/impl/memory_trace/pud_trace.cpp) permits one outstanding Request per chain, advances only on full completion, and attempts one ready-chain submission per frontend tick. It expresses dependency order, not operation identity, engine identity or microProgram membership. |

[Arithmetic builders](../../../tools/pud_operation_generator/core.py) and
[lowering](../../../tools/pud_operation_generator/lowering.py) already return a
whole program: `PhysicalLoweredProgram.primitives`, designated rows and
bindings. The lowerer is Bank-agnostic local-row code; the caller supplies
the placement. Arithmetic generation, primitive order, row allocation,
temporary-row counts and numerical behavior do not require engine metadata.
Those existing logical boundaries explain the abstraction mismatch; they do
not by themselves define a source-faithful finite control model.

The loss occurs in `generator.generate`: `arithmetic` loops over
`lowered.primitives` and appends plain physical strings; `move` similarly
loops over bits/groups. Its lowering cache shares program artifacts across
invocations, so a cached object or debug `stage` string is not an invocation ID.
Metadata retains aggregate arithmetic invocation counts and first-MUL/domain
checkpoints, but no complete operation membership/end table, and no logical
move identities. `write_gemv` adds only one CHAIN selection per output.
[Request](../../../src/ramulator/base/request.h) has physical placement,
occurrence cursor/history and a weak physical `PuDExecutionContext`, with
no logical parent operation metadata. The frontend's callback captures the
chain index; it never conveys a bbop to controller allocation.

A read-only, in-memory call/return probe of
`generate("MIMDRAM-InterMatFirst-int8", 16, 12)` found 16 distinct Bank
placements, 16 MUL calls, 32 ADD calls and 48 logical `move` calls, flattened
to 11,648 Requests. Each output emits MUL(612 Requests), move(8), ADD(46),
move(8), move(8), ADD(46). Thus logical calls, physical Requests and output
chains have different cardinalities. This probe measures generator structure,
not execution timing or a corrected engine model.

#### Investigated parent-context alternative — rejected

The audit considered one engine per existing ADD/MUL/logical-move call, or
one per explicitly combined bulk operation with several Bank-local partitions.
Under assumed E=8 and retention through operation recovery, sixteen separate
one-Bank output MULs would occupy at most eight slots; an assumed single bulk
parent could expose sixteen partitions under one slot. These are consequences
of hypothetical project models, not established SIMDRAM/MIMDRAM behavior.

The current generator keeps every domain of an output in its one Bank and
confines ranged operations to one output. Bulk grouping would change
composition/admission/completion semantics, even if it preserved the physical
arithmetic and FP8 reduction order. The alternative would need separate
operation identity/membership, partition progression, parent/child completion,
workspace ownership and a justified allocation/release model. CHAIN alone
cannot supply those semantics. The papers do not establish the missing
fan-out mechanism, exact lifetime or grouping choice.

The [common decision](../decisions/pud-multistandard-substrate.md#accepted-common-execution-model--no-finite-control-engine-capacity-2026-09-16)
rejects this direction because the available evidence does not define it
faithfully and the project chooses the DRAM-side abstraction below it.
This is investigation history, not an active proposal or an unresolved
engine-driven G5/G7 dependency. Arithmetic/lowering, GEMV grouping, physical
trace syntax and CHAIN need no engine-identity change under that boundary.

**Current correction surface:** finite admission is in
[common allocation](../../../src/ramulator/controller/pud_execution.cpp),
[protected controller records/lifecycle](../../../src/ramulator/controller/controller_base.h)
and [their implementation](../../../src/ramulator/controller/controller_base.cpp).
[GenericDDR](../../../src/ramulator/controller/impl/generic_ddr_controller.cpp)
exposes `pud_compute_engines`; the
[binding interface](../../../src/ramulator/dram/pud_binding.h) supplies pool identity.
Physical [Device contexts](../../../src/ramulator/dram/device.h) and conflict/
recovery ownership have a purpose independent of engine IDs. Existing tests
and [experiment configuration](../../../experiments/pud_gemv_baseline.py)
also refer to E. These are source dependencies, not evidence that removing E
requires new parent metadata. The plan owns implementation and validation.

### RCK source meaning and repository behavior

RCK means **Read Clock**, associated with read-data output. Cadence's
[technical overview](https://community.cadence.com/cadence_blogs_8/b/fv/posts/cadence-introduces-industry-s-first-gddr7-verification-solution)
describes CK4 as an internal divide-by-four reference derived from WCK and
RCK start/stop modes for readout. Its
[GDDR7 command listing](https://www.cadence.com/en_US/home/tools/system-design-and-verification/verification-ip/simulation-vip/memory-models/dram/gddr7.html)
also distinguishes ordinary Refresh from Refresh Management commands.
These external descriptions explain terminology; the following behavior is
verified in the repository, not inferred from a full JEDEC implementation:

- `always_on` is the default: modeled RCK stays toggling and manual
  RCKSTRT/RCKSTOP commands are rejected.
- `start_with_read` starts modeled RCK when RD/RDA issues; manual RCKSTRT is
  rejected. RCKSTOP can stop it after the read/idle timing conditions permit.
- `start_with_rckstrt` blocks RD/RDA while RCK is stopped. Waiting reads
  trigger an internal RCKSTRT, subject to device timing; the controller sets
  the state to toggling on issue, while timing edges guard subsequent reads.
- In either stoppable mode, automatic RCKSTOP requires a prior read, no waiting
  reads, and the idle threshold; timing readiness is also checked. Manual
  commands remain subject to the mode checks and device timing.
- RCKSTRT and RCKSTOP use the **column-command bus**, each for two CK4.
  A successful internal RCK issue consumes that tick's column slot, while a
  ready row command may still issue. RD/RDA recognition is explicit in the
  controller; column classification alone does not make a command a read.

The controller does not implement GDDR7 RD_MOV/WR_MOV. Their Accepted
RCK treatment is recorded in the decision and is not reinvestigated here.

### Current constraints and conventional recovery

Ordinary `ACT→ACT` uses Channel nRRD=4; GDDR7 declares no nFAW. PRADA's
activation-current argument concerns its studied compute mechanism, not a
validated GDDR7 hybrid. The current DDR4 PuD binding excludes compute ACTs
from conventional current history and omits movement current constraints.
MIMDRAM movement has no equivalent validated current exemption.

Two modeling alternatives have different consequences: carrying over those
omissions leaves current-related PuD interference unmodeled; applying a
Channel ACT-current class to ordinary and selected PuD activations in both
directions would space GB's two activations and unrelated-bank work.
Using nRRD=4 for that class would be a project proxy, not target calibration.
Neither width-scaled nRRD nor an additional nFAW is established by the evidence.

| Conventional boundary | Existing GDDR7 interval/scope and evidence limit |
| --- | --- |
| PREpb → ACT | Same-bank nRP=30; sibling-bank nRPD=2. No new PuD identity inherits these edges merely by resembling ACT. |
| PREab → ACT/REFpb | Missing timing relationships; PREab state closure does not establish recovery completion (§6). |
| RDA / WRA → ACT | Bank nRTPSB+nRP=34 / nWL+nBL+nWR+nRP=68, with reception offsets. AP marks conventional state closed immediately, so state alone cannot establish readiness. |
| REFab / REFpb → ACT | Channel nRFCab=315 / same-bank nRFCpb=105 plus Channel nRREFD=21 after REFpb. |
| RFMab / RFMpb → ACT | Channel / target Bank scope; 315/105 are placeholder values (§6). |
| PRE issue spacing | Channel nPPD=2 for PREpb/PREab; distinct from local recovery. |
| Conventional access/maintenance against current PuD protection | Common Device/controller code checks full target-bank scopes against protected invocations through recovery; all-bank GDDR7 commands target all 16 Banks of this Channel. No GDDR7 PuD binding is present. |

The common substrate's invocation-local recovery differs from conventional
Bank history. Publishing a hypothetical local PRE into Bank-wide nRP or
sibling-bank nRPD history would add disjoint-context restrictions; publishing
only shared bus/PRE-spacing edges would leave recovery local. The existing
DDR4 binding is an implementation example, not evidence selecting either
GDDR7 publication policy. Conventional preparation precedes acquisition in
the common path; a preparatory PRE is not allowed to close an already
protected Bank.

## 5. G4 — conventional timing comparison and movement analogues

### DDR4 versus GDDR7 conventional timing

These are resolved **repository-model values**, not a vendor-to-vendor
performance comparison. Sources are [DDR4](../../../python/ramulator/dram/ddr4.py)
with `DDR4_8Gb_x8 / DDR4_2400R` and
[GDDR7](../../../python/ramulator/dram/gddr7.py) with
`GDDR7_16Gb_x8 / GDDR7_28000_PAM3`, without overrides.
One DDR4 CK is **0.833 ns**; one GDDR7 CK4 is **0.571 ns**.
The table shows nominal timing parameters before reception-to-issue offsets.

| Interval | DDR4 parameter / scope | CK | ns | GDDR7 parameter / scope | CK4 | ns |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| ACT → RD | nRCD, Bank | 16 | 13.328 | nRCDRD, Bank | 30 | 17.130 |
| ACT → WR | nRCD, Bank | 16 | 13.328 | nRCDWR, Bank | 19 | 10.849 |
| PREpb → ACT | nRP, Bank | 16 | 13.328 | nRP, Bank | 30 | 17.130 |
| ACT → PREpb minimum | nRAS, Bank | 39 | 32.487 | nRAS, Bank | 60 | 34.260 |
| ACT → ACT same-bank cycle | nRC, Bank | 55 | 45.815 | nRC, Bank | 90 | 51.390 |
| WR recovery component | nWR | 18 | 14.994 | nWR | 30 | 17.130 |
| RD → PREpb | nRTP, Bank | 9 | 7.497 | nRTPSB, Bank | 4 | 2.284 |
| ACT spacing, different banks | nRRDS, Rank / nRRDL, same BankGroup | 4 / 6 | 3.332 / 4.998 | nRRD, Channel | 4 | 2.284 |
| FAW/current-window constraint | nFAW, Rank; history window 4 | 26 | 21.658 | No nFAW parameter/edge declared | — | — |

DDR4 commands here have one-tick occupancy, so these edge values need no
reception offset. GDDR7 ACT/RD/WR take two ticks and PREpb one. Thus the
GDDR7 first-issue gaps for PREpb→ACT, ACT→PREpb and RD→PREpb are respectively
29 CK4 (16.559 ns), 61 CK4 (34.831 ns), and 5 CK4 (2.855 ns). Other
constraints can delay issue further. The PRE rows describe PREpb; GDDR7
PREab's missing relationships are separate (§6).

nWR is the write-recovery **component**, not the complete WR-command-to-PRE
delay. The current conventional edge is DDR4
`nCWL+nBL+nWR=12+4+18=34 CK=28.322 ns`; GDDR7 has
`nWL+nBL+nWR=6+2+30=38 CK4=21.698 ns` nominal, or
39 CK4=22.269 ns after its WR→PREpb reception adjustment.
DDR4's Rank nRRDS and BankGroup nRRDL both apply where their scopes overlap;
same-bank nRC and the four-activation window are additional constraints.
The absence of a GDDR7 nFAW declaration is a model fact, not evidence of
unlimited physical activation current.

Movement timing correspondence is a semantic/physical analogy: capture,
restoration, precharge recovery and write recovery denote different work.
Similar cycle counts neither establish that analogy nor imply similar
physical time across the two clocks. Different counts can likewise describe
the same kind of interval. The mappings below provide the analysis supporting
the rules now selected in G4; their physical fidelity limits remain.

### LC/GB interval analysis

The MIMDRAM logical sequences represented by the existing substrate are:

```text
LC: ACT0(src), RD1(src), PRE2(src), ACT3(dst), WR4(dst), PRE5(terminal)
GB: ACT0(src), ACT1(dst), RD2(src), WR3(dst), PRE4(terminal)
```

For the alternative that retains the existing interval decomposition, the
closest conventional GDDR7 quantities are below. All values are nominal
finish-reception intervals from the illustrative preset; §3 describes the
consequences of translating them to first-issue timestamps.

| Movement interval | GDDR7 analogue in this alternative | Example CK4 | Evidence boundary / other interpretation |
| --- | --- | ---: | --- |
| LC ACT0→RD1 | nRCDRD | 30 | Conventional ACT-to-read readiness; HFF capture is an approximation. nRCDWR=19 describes a different direction. |
| LC RD1→PRE2 | nRTPSB | 4 | Existing same-bank read-to-PREpb edge. Internal HFF-read application is an approximation; DDR4 nRTP=9 is not target calibration. |
| Latest invocation ACT_MOV→PRE, LC source/destination; GB destination | nRAS | 60 | Conventional minimum active interval and MIMDRAM aggregate tRAS role support the analogy; invocation-local application is a project abstraction. |
| Destination ACT_MOV→WR_MOV, LC/GB | nRAS as a full-restoration barrier | 60 | nRCDWR=19 instead denotes ordinary ACT-to-WR acceptance. Using it would replace the existing conservative restoration barrier with earlier readiness. |
| GB source ACT0→RD2 | nRAS, source occurrence 0 | 60 | Source restoration dependency. nRCDRD would describe earlier read readiness; latest destination ACT1 history would identify a different event. |
| LC source PRE2→ACT3 and terminal PRE recovery | nRP | 30 | Conventional precharge recovery analogue; mat-selective realization is unverified. nRPD=2 is sibling-bank spacing. |
| LC WR4→PRE5 | Q(1 ns)+nWR | 2+30=32 | Relocation followed by recovery reproduces the current decomposition; application and post-WR placement are assumptions. |
| GB RD2→WR3 | Q(1 ns) | 2 | Related FIGARO relocation evidence, not a conventional GDDR7 parameter for this path. |
| GB WR3→PRE4 | nWR | 30 | Cell-write recovery analogue. Importing ordinary nWL+nBL would add external data-delivery costs; omitting them models an internal transfer. |

The [FIGARO evidence](mimdram-inter-column-data-movement.md#24-figaro-reloc-timing)
provides a guarded 1-ns interval for a related inter-subarray relocation.
Applying it to both LC and neighboring-GB paths is an assumption; neither
those exact MIMDRAM paths nor the GDDR7 circuitry were validated by that
study. At this target clock, `ceil(1000/571)=2 CK4=1.142 ns`.
The count happens to equal DDR4's two ticks, but follows from a new
quantization. Independently quantizing relocation and then adding nWR gives
the LC value above. Target-specific calibration could produce a different
interval; no such data is supplied here.

For a conditional calculation using two-tick ACT_MOV/RD_MOV/WR_MOV,
one-tick PRE, final-reception anchors, no movement nRRD, and the interval
alternative above, isolated issue times are:

```text
LC: [0, 30, 61, 90, 150, 183], terminal recovery complete at 213
GB: [0,  2, 60, 62,  93],     terminal recovery complete at 123
```

Both complete first-ACT reception at tick 1. Reception-to-recovery totals
are LC=212 CK4=121.052 ns and GB=122 CK4=69.662 ns, matching
`2*(60+30)+2+30` and `60+2+30+30`. GB destination ACT starts at tick 2
because of row-bus occupancy; destination restoration and RD→WR relocation
both allow WR at 62. These are analytic consequences of stated assumptions,
not results from an implemented GDDR7 PuD model. Other current constraints,
command envelopes, contention or timing values would change the calculation.

### Concurrency evidence boundary

The common substrate implements physical-mat-footprint intersection plus
separately modeled shared command/timing constraints, all six compute/LC/GB
pair classes, protected recovery and no-SALP. Under that abstraction, disjoint
GB endpoint footprints can progress independently. The source evidence does
not physically prove independent GDDR7 global paths or establish an
additional shared-link requirement. Carrying over the abstraction would
preserve disjoint progress; adding link serialization or Bank-wide movement
ownership would reduce it. Geometry alone does not choose between resource
models. LC source-HFF retention and directed neighboring GB connectivity are
mechanism evidence, while their realization in GDDR7 remains unverified.

## 6. G6 — conventional baseline evidence and uncertainty

### PREab and RFM meanings

**PREab is an all-bank precharge command.** In the current GDDR7 Device its
target is all 16 Banks of the addressed Channel, and its action applies
PREpb's close action to each Bank. It is **not a low-priority command by
definition**. The controller's priority queue can carry PREab, and all-bank
refresh/maintenance can produce it as a prerequisite. Scheduling priority
comes from the request path and arbitration. The identified PREab problem
is missing **timing legality/recovery edges**, not scheduler priority.

**RFM means Refresh Management**, a maintenance command family distinct from
ordinary REF. The repository provides separate RFMab/RFMpb and REFab/REFpb
identities, with all-bank/per-bank targets. GDDR7 has RFM command plumbing
but no automatic RFM policy. Manual priority injection is reachable.
The timing resolver explicitly labels `nRFMab=nRFCab` and
`nRFMpb=nRFCpb` defaults as simulator placeholders, not JEDEC equality rules.
Current values are 315/105 CK4; these do not establish calibrated RFM timing.

| Known issue | Verified fact | Consequence / missing evidence |
| --- | --- | --- |
| Approximate/guesstimated timing preset | The only preset is labeled CI/smoke/regression-only and not a vendor timing table. | Physical performance accuracy has no established error bound. A part/speed-bin table would be needed for vendor-calibrated claims. G2-B's sensing residual depends on the PRE approximation. |
| Missing PREab relationships | ACT/RD/WR→PREab protection and PREab→ACT/REFpb recovery edges are absent. | Modeled legality can allow early all-bank closure/reactivation. Applicable PREab-specific timing relationships and reception anchors are missing from supplied technical evidence. |
| Placeholder RFM timings | RFM durations default to refresh durations; manual commands are supported by plumbing tests. | Those tests establish command reachability, not physical RFM timing. A workload with no RFM never exercises these edges; a workload that includes it depends on approximate/incomplete maintenance timing. |

### DDR4 versus GDDR7 PREab legality and recovery

Direct comparison of [DDR4 timing declarations](../../../python/ramulator/dram/ddr4.py)
and [GDDR7 timing declarations](../../../python/ramulator/dram/gddr7.py) gives
the following explicit edges (nominal final-reception intervals):

| Edge | DDR4 | GDDR7 |
| --- | --- | --- |
| ACT -> PREab | Rank nRAS | Missing |
| RD -> PREab | Rank nRTP | Missing |
| RDA -> PREab | No direct edge | No direct edge |
| WR -> PREab | Rank nCWL+nBL+nWR | Missing |
| WRA -> PREab | No direct edge | No direct edge |
| PREab -> ACT | Rank nRP | Missing |
| PREab -> refresh | Rank -> REFab nRP; no REFpb command | Channel -> REFab nRP present; -> REFpb missing |

Thus DDR4 does **not** have the same broad PREab legality/recovery gap as
GDDR7. The absent direct AP-to-PREab edges are a shared, narrower observation:
[RDA](../../../src/ramulator/dram/commands/RDA.h)/[WRA](../../../src/ramulator/dram/commands/WRA.h)
close conventional state immediately, while separate AP->ACT and AP->REFab
edges retain recovery in both standards (GDDR7 also has AP->REFpb/RFMpb).
PREab does not erase those deadlines. The comparison does not prove
physical correctness of issuing redundant PREab during AP recovery in either
standard, and does not motivate an unrequested DDR4 change.

DDR4 PuD adds explicit Rank PREab->compute-open and PREab->ACT_MOV nRP,
alongside incoming PREpb/AP/REF recovery in
[compute](../../../python/ramulator/dram/ddr4_pud.py) and
[movement](../../../python/ramulator/dram/ddr4_pud_movement.py) declarations.
In the reverse direction, common
[Device protection](../../../src/ramulator/dram/device.cpp) and
[controller eligibility/release](../../../src/ramulator/controller/controller_base.cpp)
block conventional PREab against any protected invocation in its target
scope, including before first ACT and through terminal recovery. Local PuD
PRE is not PREab and does not publish Bank/Rank recovery into disjoint work.
The [DDR4 conflict tests](../../../tests/controller_scheduling/GenericDDRController/test_pud_conflicts.py)
cover PREab blocking and conventional PREab recovery before allocation.

### PREab gap observations

Existing tests cover PREpb, AP recovery, refresh prerequisites and some
RFM plumbing; they do not assert the missing PREab timing boundaries.
Read-only probes using the existing Device harness/build reproduced the gaps
and supplied the DDR4 comparison on 2026-09-16:

```text
DDR4 ACT(bank0) @ 0: earliest PREab @ 39.
GDDR7 ACT(bank0) @ 0: earliest PREab @ 2; PREpb is not ready @ 2.
DDR4 fresh closed Device, PREab @ 0: ACT and REFab first ready @ 16.
GDDR7 fresh closed Device, PREab @ 0: ACT and REFpb ready @ 1; REFab @ 30.
Both: ACT @ 0, RDA or WRA @ 100 permits PREab @ 102,
      while ACT and REFab remain blocked @ 103 by AP recovery.
```

The GDDR7 ACT→PREab observation waits only for ACT's two-tick row-bus
occupancy; ordinary ACT→PREpb nRAS would require first issue at 61. Its
PREab→ACT/REFpb observations have no recovery edge. Existing
`PREab→REFab/RFMab=nRP` and PRE-to-PRE nPPD
relationships do not fill these gaps. This observation does not establish
completeness of other baseline relationships. In particular, nRTPSB's
same-bank semantics alone do not establish the missing all-bank read-to-PRE
rule.

### Conservative PREab repair evidence and limits

The smallest repair within the existing timing-edge machinery is to add
Channel-scoped incoming/outgoing PREab edges, so every affected Bank's
conventional history contributes. Existing per-bank ACT/RD/WR close floors
can supply a project proxy; nRTPSB is not thereby established as a physical
all-bank parameter. A conservative AP variant waits for full modeled AP
recovery before PREab; this can over-delay a redundant close but avoids using
immediate Closed state as proof that recovery finished. Per-bank REF/RFM
recovery also needs to block an all-bank close. Existing all-bank maintenance
recovery, PREab->REFab/RFMab and nPPD edges can remain.

The exact Accepted edge set is in the
[G6 decision](../decisions/pud-multistandard-substrate.md#accepted-g6--gddr7-evaluation-baseline-preab-repair-and-rfm-policy-b-2026-09-17).
It is conservative relative to the repository's existing Bank recovery model,
not proven conservative against unknown GDDR7 silicon timings. Applying the
G2 reception conversion once is necessary; Bank state closure alone cannot
repair the gaps. No scheduler-priority change is implicated.

### RFM inventory, reachability, safety and timing scope

| Distinct property | Repository finding |
| --- | --- |
| DDR4 command exists? | No RFMab/RFMpb in DDR4 or its PuD variants. DDR4's maintenance command here is REFab. |
| Standards exposing both RFM commands | GDDR7, HBM3, HBM4, DDR5_RFM and its DDR5_RFM_VRR extension; plain DDR5 does not add them. |
| GDDR7 command can be injected? | Yes. Generated registration, prerequisites and manual `priority_send` tests support both scopes. |
| GDDR7 automatic policy generates it? | No built-in RFM policy in GDDR7Controller or its selected ordinary refresh managers; command plumbing does not imply generation. |
| PuD conflict safety exists? | Common protected-target checking covers the command's target Banks through recovery; this is reusable protection, not an already implemented/tested GDDR7 PuD binding. |
| Physical RFM timing calibrated? | No. GDDR7 defaults nRFMab/nRFMpb to nRFCab/nRFCpb, 315/105 CK4 in this preset, explicitly as placeholders. |

Sources: [DDR5_RFM](../../../python/ramulator/dram/ddr5_rfm.py),
[DDR5_RFM_VRR](../../../python/ramulator/dram/ddr5_rfm_vrr.py),
[HBM3](../../../python/ramulator/dram/hbm3.py),
[HBM4](../../../python/ramulator/dram/hbm4.py),
[GDDR7 controller tests](../../../tests/controller_scheduling/test_gddr7.py).
An optional [RFMManager](../../../src/ramulator/controller/plugin/impl/rfm_manager.cpp)
exists elsewhere, but setup requires Rank, absent in GDDR7; it is not evidence
of an automatic GDDR7 policy. A future manager or manually injected Request
would be a separate generation path requiring an explicit workload choice.

[RFMab](../../../src/ramulator/dram/commands/RFMab.h) targets all Banks in the
addressed scope and may require PREab; [RFMpb](../../../src/ramulator/dram/commands/RFMpb.h)
targets one Bank and may require PREpb. Common Device target traversal and
controller pre-prerequisite eligibility can block either from overlapping a
protected PuD region even though RFM physical timings are uncalibrated.
Conversely, preserved numerical maintenance recovery must feed new PuD opening
identities in a future binding; conflict protection alone does not establish
that the recovery duration is physically accurate.

**Policy A alternative:** include RFM traffic in validated GDDR7 PuD timing.
This expands incoming/outgoing maintenance validation and needs applicable
RFM timing evidence; refresh-derived placeholders do not supply that evidence.
**Policy B evidence boundary (selected in the canonical decision):** keep
plumbing and conflict protection, generate no
RFM in the selected evaluation workload/maintenance configuration, and make
no validated RFM-latency claim. This retains manual safety probes and future
policy integration. The evaluation contract must cover plugin/manager and
manual-input generation, with zero RFM checked in its traces; it need not
remove commands or reject them globally.

The **project GDDR7 evaluation baseline** denotes the fixed repository
architecture-evaluation configuration, not vendor-calibrated timing accuracy
or JESD239 timing completeness.
The underlying source preset still says CI/smoke/regression-only and has not
been changed. Its use and the repair/Policy B are Accepted project choices
in the [G6 decision](../decisions/pud-multistandard-substrate.md#accepted-g6--gddr7-evaluation-baseline-preab-repair-and-rfm-policy-b-2026-09-17);
they do not supply a timing-error bound or waive ordinary REF/PuD recovery
validation. The PREab repair is conservative only relative to existing modeled
recovery, not a vendor/JEDEC-calibrated GDDR7 PREab timing specification.
Reachable nRFMab/nRFMpb placeholders remain uncalibrated even when separate
injected-command safety tests pass.

## 7. Evidence summary and unresolved questions

| Gate | Evidence / derived result | Remaining uncertainty / fidelity limit |
| --- | --- | --- |
| G1 | Representative geometry; x8/prefetch-32 model; 2-KiB page, 32-B burst, H-equivalent=8, 64 groups | Physical wiring is unverified and realistic GPU PA hashing deferred; modeled geometry, provisional PA integration and GB topology are selected in the decision |
| G2 | PRADA/DDR4 derivation; unscaled A=(16,8,58,50,62), B=(16,8,52,43,62); PRE=30 | Physical portability/calibration remains a fidelity limit; phase policy and anchors are now selected in the decision |
| G3 | Current DDR4 charges primitives; paper engines represent bbop/microProgram contexts; inspected public MIMDRAM/Proteus paths expose no finite engine occupancy | Prior-work control-to-BLP/SALP connection remains insufficient for a faithful finite model; common omission and bus/RCK policy are selected in the decision, without engine-driven G5/G7 dependencies |
| G4 | MIMDRAM sequences, related FIGARO evidence, conventional timing analogues and conditional timelines | Selected analogues, selective close and relocation remain target physical-fidelity assumptions, not open policy choices |
| G6 | DDR4 has core PREab edges absent in GDDR7; both omit direct AP->PREab; RFM plumbing/protection and calibration are distinct | Baseline, conservative PREab repair and Policy B are selected in the decision; implementation/validation remains pending, and physical PREab/RFM calibration remains unavailable |

Project choices and status are maintained only in the
[canonical decision](../decisions/pud-multistandard-substrate.md); the
[implementation plan](../plans/pud-multistandard-substrate-plan.md) tracks their
first code consumers. The evidence itself does not confer project acceptance.
