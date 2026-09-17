# HBM3 PuD modeling reference

Investigation: 2026-09-17, branch `feature/pud-multistandard-substrate`,
HEAD `74b7a59210f7da85191e2066cbe95213a5a75730`; working tree clean at entry.
Scope: HBM3 G1/G2/G3/G4/G6 only. This document records source facts,
derivations, alternatives and fidelity limits, not accepted project decisions.
The [canonical decision](../decisions/pud-multistandard-substrate.md) owns
modeling status; the [plan](../plans/pud-multistandard-substrate-plan.md)
owns first consumers. The common no-finite-control-engine policy remains fixed.
G5/G7 were not investigated. No production code, generated source or tests
were modified during the HBM3 investigation.

## 1. Evidence and inspection boundary

The required common decision, plan, original
[source audit](pud-multistandard-substrate-audit.md), and complete
[GDDR7 reference](gddr7-pud-modeling-reference.md) were read. The last is a
methodological precedent, not authority for HBM3 physical parameters.

Primary repository sources inspected:

- Complete [HBM3 declaration](../../../python/ramulator/dram/hbm3.py),
  [generated HBM3 registration](../../../src/ramulator/dram/impl/HBM3.cpp),
  [timing serializer](../../../python/ramulator/dram/spec.py), and
  [runtime spec loader](../../../src/ramulator/dram/dram_spec.cpp).
- Complete [HBM34 controller](../../../src/ramulator/controller/impl/hbm34_controller.cpp),
  [HBM controller base](../../../src/ramulator/controller/impl/hbm_controller_base.cpp),
  its [header](../../../src/ramulator/controller/impl/hbm_controller_base.h),
  [ControllerBase](../../../src/ramulator/controller/controller_base.cpp),
  [Device](../../../src/ramulator/dram/device.cpp), and
  [node timing](../../../src/ramulator/dram/node.cpp).
- Conventional ACT, RD/WR/AP, PRE and REF/RFM templates under
  [commands](../../../src/ramulator/dram/commands);
  [mapper base](../../../src/ramulator/controller/addr_mapper/addr_mapper_base.cpp),
  [RoBaRaCoCh](../../../src/ramulator/controller/addr_mapper/impl/ro_ba_ra_co_ch.cpp),
  [CacheLineInterleave](../../../src/ramulator/memory_system/channel_mapper/impl/cache_line_interleave.cpp).
- Complete [HBM34PerBankRefresh](../../../src/ramulator/controller/refresh/impl/hbm34_per_bank_refresh.cpp),
  [AllBank](../../../src/ramulator/controller/refresh/impl/all_bank.cpp) and
  [PerBank](../../../src/ramulator/controller/refresh/impl/per_bank.cpp).
- Complete [HBM3 Device tests](../../../tests/device_timings/test_hbm3.py),
  HBM34 [pairing](../../../tests/controller_scheduling/HBMController/test_hbm34_controller.py),
  [timing](../../../tests/controller_scheduling/HBMController/test_hbm34_timing.py)
  and [refresh](../../../tests/controller_scheduling/HBMController/test_hbm34_refresh.py)
  tests; HBM all-bank scope tests in
  [test_all_bank_refresh.py](../../../tests/controller_scheduling/test_all_bank_refresh.py);
  HBM3 [smoke](../../../tests/smoke/testcases/hbm3.py) and
  [latency/throughput](../../../tests/latency_throughput/testcases/hbm3.py) configurations.

Generated C++ supplies identity, handlers and metadata; resolved numeric edges
come from Python. There is no separate handwritten HBM3 timing implementation.
In-memory configuration serialization and existing local Device/controller
harness probes corroborated the source findings below. Commands used
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. LD_LIBRARY_PATH=.` with
`ramulator2-venv/bin/python3 -c`; no source regeneration or rebuild occurred.
These are observations from the existing checkout build, not a new certified
binary baseline, full regression run, or silicon validation.

### External evidence ledger

**HBM3-specific interface evidence:** JEDEC JESD238 (January 2022), §§2,
3.1.2, Table 4, and command descriptions, was inspected through a
[third-party transcription of the primary standard](https://studylib.net/doc/28350036/jesd238-hbm3).
The JEDEC-hosted announcement was unavailable to the browser. Thus this is
standard-text evidence with mirror/transcription provenance, not an
authenticated vendor datasheet. It describes two 32-bit PCs sharing row/column
command buses, 256-bit accesses, 1-KB pages per PC, and SID as Stack ID/bank
address extension. These corroborate the modeled interface, not internal mats.
The supplied “two pages per Channel, 1 KB per page” is consistent with one
bank-page in each PC; it does not mean only two open bank rows can exist in a
Channel.

**Older-HBM representative evidence:** O'Connor et al.,
[*Fine-Grained DRAM*, MICRO 2017](https://research.nvidia.com/sites/default/files/pubs/2017-10_Fine-Grained-DRAM%3A-Energy-Efficient/oconnor_and_chatterjee.micro2017.pdf),
§2.2, printed PDF page 3 and Fig. 3, explicitly describes an HBM2 example:
16K rows/bank, 32 subarrays/bank, 512 rows/subarray, 512×512 mats,
sixteen mats spanning a 1-KB row, and sixteen bits/mat over two internal cycles
per 32-byte access. The paper uses “channel” for an HBM2 pseudochannel.
Its 128-bit internal output per cycle and aggregate 256-bit access are
different widths. This is independent support for a representative 1-KiB
organization; it is not measured HBM3 geometry or sixteen simultaneous HFFs.

The earlier HPCA 2017 organization in the GDDR7 reference describes a different
2-KiB/32-mat example. Neither older organization is a universal HBM rule.
No inspected primary source establishes HBM3 mat dimensions, rows/subarray,
physical subarray count, HFF count, mat-selective PRE wiring or a PuD
inter-mat path. A part-specific array/datapath description or applicable circuit
study would be required for those stronger claims.

## 2. Actual repository hierarchy and conventional model

The complete address vector is:

```text
Channel / PseudoChannel / Sid / BankGroup / Bank / Row / Column
```

The node tree stops at Bank; Row is stored in the Bank row-state map, and
Column is a compact burst selector after mapping. There are no Rank, Chip,
Subarray or Mat nodes. Sid distinguishes bank sets under a PC; it participates
in bank identity, same/sibling-Sid CAS timing, and refresh-set bookkeeping.
It is neither an independent command bus nor a DDR4 Rank or participating
PuD Chip. The source does not map each Sid to a unique physical DRAM die.

One Device/controller covers one Channel with **both PCs**. The width field
is 32 bits per accessed PC transaction, not a claim that the physical Channel
has only 32 data pins. With prefetch 8, `32*8/8=32 B` per transaction.
`256 columns*32 bits=8192 bits=1 KiB` per modeled Bank row in a PC;
`256/8=32` compact burst columns. An ACT opens one such addressed Bank row,
not both PCs' rows together. Independent controllers are needed for additional
Channels; a stack is not automatically instantiated.

| Organization | Density field, Mb | PCs | Sids/PC | BG/Sid × Banks/BG | Rows/Bank | Derived bytes/Channel |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| HBM3_4Gb | 4096 | 2 | 1 | 4×4 | 16384 | 512 MiB |
| HBM3_8Gb_8hi | 8192 | 2 | 2 | 4×4 | 8192 | 512 MiB |
| HBM3_16Gb_8hi | 16384 | 2 | 2 | 4×4 | 16384 | 1 GiB |
| HBM3_32Gb_8hi | 32768 | 2 | 2 | 4×4 | 32768 | 2 GiB |
| HBM3_32Gb_16hi | 32768 | 2 | 4 | 4×4 | 32768 | 4 GiB |

These capacities are products of repository dimensions, not verification of
every preset name against a physical stack. The density field is not a C++
address dimension. The resolver uses `density/sid_count` for nRFC selection;
its results need not be inferred from the capacity product. For these rows,
nRFC resolves to 416/416/560/720/560 CK. The physical density interpretation
and full part-specific preset calibration remain unverified. The smallest
candidate scope uses only `HBM3_8Gb_8hi / HBM3_6400Mbps`, already used by
the HBM3 Device, controller and smoke tests: 64 Banks/Channel, 32 per PC.

Ordinary `RoBaRaCoCh` actually consumes compact Column, then PC, Sid, BG,
Bank, Row from low to high bits after the transaction offset. It invents no
Rank. With one Channel and the selected organization, an arithmetic
compatibility map is:

```text
byte offset = PA % 32
B   = (PA / 32) % 32
PC  = (PA / 1024) % 2
Sid = (PA / 2048) % 2
BG  = (PA / 4096) % 4
Bank= (PA / 16384) % 4
Row = PA / 65536
```

Divisions are integer. Default CacheLineInterleave stripes additional
Channels at transaction granularity (32 B), separately from intra-Channel
decode. This is simulator compatibility mapping, not GPU physical hashing.
Explicit PuD placement need not supply PA and remains a separate concept.

### Tick, occupancy and edge scheduling

Python presets and command durations are in CK. `tick_multiplier=2`
doubles all timing values except rate; command durations become integer ticks.
One controller tick advances one CK edge, nominally `625/2=312.5 ps`.
The serializer instead exports `tCK_ps=625//2=312`; ControllerBase stores
an integer, reports `get_tCK()=0.312 ns`, and uses it in throughput time.
[Test metadata](../../../tests/validation_common.py) independently computes
0.3125 ns from the original preset. This is a real reporting inconsistency.
Tick scheduling itself uses integers; frontend clock ratios do not turn a
controller tick into a full CK. No separate WCK simulation is declared here.

The tick prologue increments the initial zero clock, so odd ticks are rising,
even ticks falling. A rising tick tries a column command, then a row command;
both can issue at the same timestamp if otherwise legal. A falling tick tries
only PREpb/PREab. Other row commands, even one-tick REF/RFM, start on rising
ticks. The two command buses are **Channel-wide and shared by both PCs**.

| Commands | Bus | CK occupancy | Tick occupancy | Start edges |
| --- | --- | ---: | ---: | --- |
| ACT | Row | 1.5 | 3 | Rising, reception R-F-R |
| PREpb / PREab | Row | 0.5 | 1 | Rising or legal falling |
| REFab / REFpb / RFMab / RFMpb | Row | 0.5 | 1 | Rising only |
| RD / WR / RDA / WRA | Column | 1 | 2 | Rising only |

Generated Channel edges enforce each multi-tick bus occupancy. The controller
also limits each bus to one start per eligible tick. There are not independent
row/column buses per PC.

HBM34 records the last rising row command. Its pairing falling edge is
`issue+3` for the literal ACT identity, otherwise `issue+1`.
At that edge, after occupancy and other timing checks:

- A PRE to the other PC may be PREpb or PREab.
- After same-PC PREab/REFab/RFMab, no falling PRE is allowed.
- After another same-PC row command, only PREpb to a different bank is allowed.
  The bank key is `(Sid*BG_count+BG)*Banks_per_BG+Bank`.
- Outside the recorded pairing edge, falling PRE is allowed by the edge
  filter, still subject to timing. Idle rising edges do not create a new pair.

Thus ACT at tick 1 occupies ticks 1–3, can pair with legal PRE at 4, and the
next rising ACT start is at least 5. A one-tick REF at 1 can pair with legal
PRE at 2; another REF cannot start until 3. Different-PC PRE commands can
start on adjacent edges; same-PC nPPD prevents that in the selected preset.
Device-only tests do not enforce the controller's parity/pairing filter.

### Timing scopes and resolved values

The following are source values, before reception offsets. Physical times use
the nominal exact half-CK; current runtime reporting is 0.16% shorter.

| Parameter | CK | Ticks | Nominal ns |
| --- | ---: | ---: | ---: |
| nBL / nCL / nCWL | 2 / 20 / 10 | 4 / 40 / 20 | 1.25 / 12.5 / 6.25 |
| nRCDRD / nRCDWR | 31 / 15 | 62 / 30 | 19.375 / 9.375 |
| nRAS / nRP / nRC | 45 / 26 / 72 | 90 / 52 / 144 | 28.125 / 16.25 / 45 |
| nRTP / nWR | 9 / 33 | 18 / 66 | 5.625 / 20.625 |
| nCCDS / nCCDL / nCCDR | 2 / 4 / 3 | 4 / 8 / 6 | 1.25 / 2.5 / 1.875 |
| nRRDS / nRRDL / nFAW | 4 / 5 / 24 | 8 / 10 / 48 | 2.5 / 3.125 / 15 |
| nWTRS / nWTRL / nRTW | 7 / 10 / 20 | 14 / 20 / 40 | 4.375 / 6.25 / 12.5 |
| nPPD | 2 | 4 | 1.25 |
| nRFC / nRFCpb | 416 / 320 | 832 / 640 | 260 / 200 |
| nRFMab / nRFMpb | 416 / 320 | 832 / 640 | Uncalibrated aliases |
| nRREFD | 8 | 16 | 5 |
| nREFI / nREFIpb | 6240 / 195 | 12480 / 390 | 3900 / 121.875 |

PC timing covers same-direction data-bus occupancy, read/write turnarounds,
nRRDS and four-ACT nFAW, nPPD, PREab and all-bank maintenance.
Sid timing covers same-Sid read/read and write/write nCCDS and sibling-Sid
read/read nCCDR. BG timing covers nCCDL, long write/read turnaround and nRRDL.
Bank timing covers activation, access, close, AP recovery, and per-bank
maintenance. There is no declared sibling-Sid write/write nCCDR; per-PC
nBL still applies. PC0's histories do not publish into PC1's timing domains.
Ordinary node traversal retains Sid/BG/Bank and sibling-edge updates.

## 3. G1 geometry and explicit-placement candidate

A minimal representative candidate is a single named profile for the selected
preset, with sixteen 512×512 mats per Bank-local subarray, 512 rows/subarray,
and one logical participating 32-bit slice. A profile field currently named
`chips=1` would denote that slice only; it must not mean one stack die or
reinterpret Sid. The representative premise comes from the HBM2 source in
§1, independently of GDDR7.

Conditional arithmetic under the existing exhaustive all-mats-per-burst
placement contract is:

```text
page                 = 256*32 = 8192 bits = 16*512 bits
burst                = 32*8 = 256 bits = 32 B
H-equivalent         = 256/16 = 16 positions per mat per logical transfer
groups/mat-row       = 512/16 = 32 = 256/8 bursts/page
subarrays/Bank       = 8192/512 = 16
bytes/subarray       = 16*512*512/8 = 512 KiB
bytes/Channel        = 2 PCs*2 Sids*4 BG*4 Banks*16 subarrays*512 KiB
                     = 512 MiB
```

Sixteen mats/page is justified **conditionally** by a published older-HBM
organization, not proved for HBM3 by page-size division. Sixteen H-equivalent
positions describe an aggregate logical 32-B access, not sixteen physical HFFs
or sixteen bits/mat in one physical internal cycle. The older source's two
internal transfer cycles are not a separate clock domain in this abstraction;
no internal-cycle-to-HBM-CK timing relationship is established. Adding a
second internal-cycle state machine would need new evidence; choosing H=8
with these sixteen mats would cover only 128 bits and would require changing
the common burst/group contract.

Proposed explicit placement is
`Channel, PseudoChannel, Sid, BankGroup, Bank, Row, MatRange, optional Group`.
Candidate row subdivision is `Subarray=Row/512, LocalRow=Row%512`.
Candidate tables use ascending mat/position order, consecutive cells
`16*Group+h`, and identity burst-to-group mapping. For the ordinary scalar
compatibility map, `slot=8*byte_offset+bit`, `Mat=slot/16`,
`h=slot%16`; the hierarchy decode remains §2. Those mappings are invertible
conventions, not measured wiring.

The minimum profile also needs bounds, exact capacity/inverse coverage and
an explicit GB successor table. A concrete bounded topology candidate is
`m -> m+1`, m=0..14, within this same Bank/subarray/slice, no reverse or wrap.
Published HBM3 does not establish this path. Restricting GB entirely until
circuit evidence arrives would prevent a complete LC/GB primitive binding;
accepting this representative convention permits architecture evaluation with
that fidelity limitation. No cross-PC, cross-Sid, cross-Bank, cross-subarray
or cross-Channel path is inferred.

## 4. G2 physical phases and clock anchors

The [existing PRADA derivation](ddr4-pud-timing-reference.md) supplies
tOC=5 ns, modeled tCS=4 ns, tN=35 ns, and the calibrated residual
`tSR=81.32-35-5-4-13.328=23.992 ns`. tSR is a project-derived residual,
not independently measured HBM3 sensing time.

One clear portability candidate retains those physical phase durations,
quantizes each separately to the exact nominal HBM half-CK, and uses target
PRE recovery separately. This is supported as a transparent experiment:
there is no HBM3 evidence that slower PRE makes sensing proportionally faster.
It remains hypothetical HBM3 PRADA calibration, not an automatic consequence
of GDDR7 acceptance. No ACT-overhead envelope or sensitivity case is introduced.

With `q=625/2=312.5 ps`:

| Phase | Physical input | Calculation | Candidate ticks | Quantized ns |
| --- | ---: | --- | ---: | ---: |
| A* | 9 ns | ceil(9000/312.5) | 29 | 9.0625 |
| A | 4 ns | ceil(4000/312.5) | 13 | 4.0625 |
| A_S* | 32.992 ns | ceil(32992/312.5) | 106 | 33.125 |
| A_S | 27.992 ns | ceil(27992/312.5) | 90 | 28.125 |
| N | 35 ns | ceil(35000/312.5) | 112 | 35 |
| PRE recovery | 26 CK from HBM3 | 26*2 | 52 | 16.25 |

Keeping the phases changes continuous temporal NOT to
`32.992+35+16.25=84.242 ns`. Recalibrating tSR to preserve 81.32 ns would
instead produce `tSR=21.070 ns` and sensing phases 30.070/25.070 ns
(97/81 ticks); no HBM3 circuit evidence supports that compensation.
Target circuit calibration is unavailable.

There is a real clock-policy alternative: retain the exported 312-ps runtime
duration as a bounded approximation. Independent quantization then gives
`(29,13,106,90,113)`, with nRELOC=4. Simply retaining N=112 but reporting
312 ps would describe 34.944 ns, below its 35-ns input.
The exact-half-CK candidate therefore requires a separately reviewed precision
correction through serialization, runtime duration and reporting before its
physical-time claims are executable. It need not change conventional integer
command timestamps. A reporting-only relabel without fixing all relevant
consumers would not resolve the inconsistency.

For occupancy c, final reception is `R=I+c-1`. Repository edge conversion is:

```text
I_follow - I_before >= nominal_interval_ticks + c_before - c_follow
recovery_done = I_PRE + c_PRE - 1 + nRP
```

These common semantics apply directly **after** CK-to-half-tick conversion.
HBM adds eligible-edge rounding and falling-PRE pairing, not a second
reception adjustment. With the §5 candidate, A_S*→N has gap
106+3-1=108; A→A has gap 13 but two rising-only starts require at least
14 ticks. PRE→ACT_MOV has gap 52+1-3=50; its earliest start then depends on
PRE parity. Terminal PRE has c=1, so completion is I_PRE+52 on either parity.
A completion callback itself need not wait for a rising edge.

Python timing inputs remain CK-valued. The independently quantized half-tick
tuple corresponds to `(14.5,6.5,53,45,56) CK` at the serializer boundary,
not the integer tick tuple entered as CK and doubled again. Occurrence-only
edges require the same single reception adjustment as serialized local edges.
Bus occupancy and issue parity are separate constraints; summing physical
phase counts alone does not necessarily predict an executable timeline.

## 5. G3 resource and concurrency candidate

| Role | Candidate Channel resource | Occupancy, ticks | Start/pairing convention |
| --- | --- | ---: | --- |
| A / A* / A_S / A_S* | Row bus | 3 | Rising; ACT-like pairing edge I+3 |
| N | Row bus | 1 | Rising; ordinary one-tick row pairing I+1 |
| ACT_MOV | Row bus | 3 | Rising; ACT-like pairing I+3 for each endpoint |
| RD_MOV / WR_MOV | Column bus | 2 | Rising |
| PuD PREpb, including LC source PRE | Row bus | 1 | Both edges under existing PC/bank pairing |

ACT/column/PRE occupancies follow the HBM3 representation; N's one-half-CK
envelope is an explicit encoding candidate with no physical validation.
No GDDR7 two-tick activation is imported. Extending literal ACT recognition
to the PuD activation roles is necessary: merely classifying them as row
commands would record the wrong pairing edge.

One shared ownership/occurrence/completion model can retain
`[Channel,PC,Sid,BG,Bank]` identity. Same-Bank disjoint mats may overlap
only in the same execution subarray; different-subarray work in that Bank
serializes under no-SALP. Distinct PCs/Sids identify genuinely distinct Banks.
They can progress concurrently subject to shared Channel issue resources.
PC-local nPPD and maintenance histories should not serialize the other PC;
that is a target resource property, not a footprint-policy exception.
Finite engines, engine pools and engine admission remain absent.

Candidate shared publication is Channel bus occupancy plus **addressed-PC
nPPD for invocation PRE**. PuD local phase/PRE recovery must not publish
ordinary Bank recovery or PC-wide PRE→REF recovery into disjoint invocations.
Conventional timing still descends through the full hierarchy. Conventional
PRE/AP/REF/RFM recovery must feed new opening identities at the same PC/Bank
scopes, including the conventional ACT→opening nRC floor needed after early AP.
Protection excludes ordinary array commands and matching maintenance scopes
through terminal recovery, including pre-ACT reservations.

The candidate retains the common compute-current omission and existing
movement-current/external-DQ omissions: no PuD participation in conventional
nRRDS/nRRDL/nFAW, nRC between GB endpoint activations, or external
nBL/CAS/DQ-turnaround history for internal RD_MOV/WR_MOV. Ordinary commands
retain all of those applicable constraints. These are uncalibrated PuD
omissions, not HBM3 exemptions proved by separate PC timing. Internal shared
transfer wiring is not established; no additional Bank-wide movement owner
or GB-link owner is inferred.

## 6. G4 movement candidate and independent calculations

The [common movement authority](../decisions/mimdram-movement-timing-and-resource-model.md)
and [technical evidence](mimdram-inter-column-data-movement.md) provide the
logical LC/GB graphs and guarded FIGARO-derived tRELOC=1 ns assumption.
No HBM3-specific evidence found here requires replacing that assumption.

```text
LC: ACT0(src), RD1(src), PRE2(src), ACT3(dst), WR4(dst), PRE5(terminal)
GB: ACT0(src), ACT1(dst), RD2(src), WR3(dst), PRE4(terminal)
nRELOC = ceil(1000/312.5) = 4 ticks = 1.25 ns
```

Under the compatibility alternative, ceil(1000/312)=4 as well, representing
1.248 ns. Equality of the count is a fresh derivation, not copied calibration.

| Dependency | HBM3 analogue | Nominal ticks | First-issue gap before edge filtering |
| --- | --- | ---: | ---: |
| LC ACT0→RD1 | nRCDRD | 62 | 63 |
| LC RD1→PRE2 | nRTP | 18 | 19 |
| Applicable latest ACT_MOV→PRE | nRAS | 90 | 92 |
| LC PRE2→ACT3 | nRP | 52 | 50 |
| LC/GB destination ACT→WR | nRAS restoration barrier | 90 | 91 |
| GB source ACT0→RD2 | nRAS, source occurrence 0 | 90 | 91 |
| LC WR4→PRE5 | nRELOC+nWR | 4+66=70 | 71 |
| GB RD2→WR3 | nRELOC | 4 | 4 |
| GB WR3→PRE4 | nWR | 66 | 67 |
| Terminal PRE→completion | nRP | 52 | 52 |

nRCDRD models read readiness; nRTP models read-to-close; nRAS is the retained
minimum-active/full-restoration proxy. Ordinary nRCDWR=30 ticks is earlier
write acceptance, not the same restoration barrier. nRP models close recovery.
nWR models internal write recovery without importing conventional external
delivery `nCWL+nBL`; conventional WR→PRE remains 90 nominal ticks,
91 first-issue ticks. Applying these analogues to selective mat paths is a
project candidate, not validated HBM3 circuitry.

Conditional isolated schedules starting at rising tick 1, with §5 resources,
exact-half-CK units and no contention, are:

```text
LC issues [1, 65, 93, 143, 235, 306]; completion 358
GB issues [1,  5, 93,  97, 164];      completion 216
```

LC RD readiness at 64 waits until rising 65; destination WR readiness at
234 waits until 235. GB destination ACT waits past three occupied row ticks
to rising 5; RD readiness at 92 waits until 93. Terminal PREs at even
306/164 are outside the preceding row command's pairing window and are legal.
First ACT reception is tick 3: reception-to-completion intervals are
355 ticks=110.9375 ns and 213 ticks=66.5625 ns. First-issue-to-completion
intervals are 357/215 ticks. The phase sums 354/212 omit one tick of
unhidden edge alignment; they are not executable latency oracles by themselves.
These are analytic schedules, not implemented HBM3 PuD measurements.

LC uses equal mat ranges and ordered groups; GB uses singleton endpoints on
the §3 directed neighbor table. Both remain within one Bank and subarray,
hence also within one PC and Sid. No cross-PC/Bank/subarray move is supported.
The common topology representation needs new HBM3 **profile contents and
explicit physical convention**, not a cross-hierarchy movement mechanism.
Mat-selective close, source-HFF retention across LC PRE and disjoint-footprint
progress remain abstraction assumptions. Terminal recovery holds the complete
union footprint until PRE reception+nRP, then releases before exact-once
completion; LC source PRE does not release ownership.

## 7. G6 baseline findings and bounded repair candidate

### Existing protections and omissions

HBM3 independently has the following relationships. Nominal values are ticks;
the serializer applies reception offsets once.

| Relationship | Current scope/value | Assessment |
| --- | --- | --- |
| ACT→PREpb / PREab | Bank / PC, nRAS=90 | Already adequate for modeled minimum-active floor |
| RD→PREpb / PREab | Bank / PC, nRTP=18 | Already adequate for modeled read-close floor |
| WR→PREpb / PREab | Bank / PC, nCWL+nBL+nWR=90 | Already adequate for modeled write-close floor |
| PREpb / PREab→ACT | Bank / PC, nRP=52 | Already present; do not copy GDDR7 repair |
| ACT→ACT | Bank nRC=144; PC/BG current edges also apply | Existing same-Bank recovery floor |
| RDA / WRA→ACT | Bank 70 / 142 | Existing AP recovery; ACT nRC also remains |
| ACT→REFab/RFMab | PC nRC=144 | Already present |
| ACT→REFpb/RFMpb | Bank nRC=144 and PC nRRDS=8 | Already present |
| PREpb/PREab→REFab/RFMab | PC nRP=52 | Already present |
| PREpb→REFpb/RFMpb | Bank nRP=52 | Already present |
| PREab→REFpb/RFMpb | Missing | Must repair before mixed maintenance/PuD use |
| RDA/WRA→REFab/RFMab | PC 70 / 142 | Already present |
| RDA/WRA→REFpb/RFMpb | Missing | Must repair: immediate Closed state bypasses AP drain |
| REFab/RFMab→ACT, PREab | PC nRFC/nRFMab | Existing recovery into these commands |
| REFpb/RFMpb→ACT | Bank nRFCpb/nRFMpb; PC nRREFD | Existing addressed-Bank and interbank recovery |
| Maintenance→other maintenance / PRE | Incomplete; only REFpb→REFpb PC nRREFD plus above edges | Must repair reachable overlap; edge parity alone is insufficient |
| AP→PREpb/PREab | No direct AP edge | Do not automatically add GDDR7's full-AP-drain rule |

RDA/WRA immediately close the software row state; their ACT/REFab deadlines
survive later PRE and are not erased. JESD238 §6.3.2.3.1 permits overlap of AP
with explicit precharge, so the missing direct AP→PRE edge alone is not proof
that a full-drain PRE rule is required. Exact redundant-PRE/AP parity fidelity
needs further evidence; the candidate repairs the demonstrably unprotected
subsequent REFpb/RFMpb instead. This avoids an unjustified symmetric repair.

All-bank commands use `BankTarget::All`, but the actual target set is every
Bank matching the supplied ancestry vector. The automatic AllBank manager
uses PC plus wildcard Sid/BG/Bank/Row/Column, covering all 32 Banks of that PC
in the selected preset. Manual full coordinates can narrow an “ab” command
to fewer Banks; this API behavior is not a physical all-bank encoding.
A bounded evaluation and safety tests need canonical PC-wide vectors.
No synthetic Rank or Channel-wide refresh of both PCs is necessary.

### Source-backed probes

On fresh Devices with selected presets, the existing harness returned:

| Issued history | First-ready observations, Device ticks |
| --- | --- |
| PREab at 0, PC-wide | ACT 50; REFab 52; REFpb/RFMpb 1 |
| REFab at 0, PC-wide | ACT 830; PREab 832; PREpb and every REF/RFM identity 1 |
| REFpb at 0 | Same-Bank ACT 638; repeated REFpb 16; PREpb/PREab/REFab/RFMab/RFMpb 1 |
| RFMab at 0, PC-wide | ACT 830; PREab 832; PREpb and every REF/RFM identity 1 |
| RFMpb at 0 | Same-Bank ACT 638; all tested PRE/REF/RFM identities 1 |
| ACT 0, RDA 200 | ACT 269; REFab/RFMab 271; REFpb/RFMpb 201 |
| ACT 0, WRA 200 | ACT 341; REFab/RFMab 343; REFpb/RFMpb 201 |

The late AP cases deliberately outlive ACT's nRC deadline to isolate the
missing column-to-per-bank-maintenance edge. Device tick 0 is valid in the
harness; it is not HBM34's first rising tick.

HBM34 priority-injection probes separately produced
`[(1,PREab),(3,REFpb)]`, `[(1,REFab),(3,REFpb)]`,
`[(1,REFab),(3,REFab)]`, and `[(1,REFpb),(3,REFab)]`
for same-PC targets. Thus the controller's rising-only maintenance rule does
not cover the missing recovery intervals. These observations corroborate the
declaration inventory; they do not certify all timing relationships.

### Small conservative repair alternative

The smallest edge-based candidate retains existing edges and supplies missing
recovery for affected scopes, rather than serializing the whole Channel.
Let AB={REFab,RFMab}, PB={REFpb,RFMpb}, and D(command) be its existing
nRFC/nRFM duration. All intervals below are nominal final-reception ticks.

| Added relation | Scope | Candidate interval |
| --- | --- | --- |
| PREab→PB | PC | nRP |
| RDA→PB / WRA→PB | Bank | nRTP+nRP / nCWL+nBL+nWR+nRP |
| AB→AB and AB→PB | PC | D(preceding AB) |
| AB→PREpb | PC | D(preceding AB); existing AB→PREab remains |
| PB→AB and PB→PREab | PC | D(preceding PB), so any busy Bank blocks the covering operation |
| PB→PB and PB→PREpb | Same Bank | D(preceding PB) |
| Missing PB→PB spacing pairs | PC | nRREFD; retain existing REFpb→REFpb |

Same-Bank full recovery and PC interbank spacing both apply where relevant.
The Bank rule does not replace refresh-set ordering. The PB→covering-command
rules can over-delay commands to unaffected Sids in the same PC; their purpose
is conservative protection within the repository's PC-wide all-bank model.
RFM entries protect reachable manual traffic using uncalibrated durations;
they do not calibrate RFM. These are project repair candidates based on existing
recovery floors, not a complete JEDEC timing matrix or silicon-safe bound.

The source's nRREFD fallback says `max(3 CK,8 ns)`, which at 625 ps is
`max(3,ceil(8000/625))=13 CK=26 ticks=8.125 ns`.
The preset explicitly supplies 8 CK=16 ticks=5 ns and `setdefault` preserves it.
A narrow conservative candidate uses 13 CK, matching the documented fallback;
this is a source-consistency repair, not independently authenticated speed-bin
calibration. nREFI=6240 CK already equals its fallback.
The other direct preset timings and refresh-derived RFM aliases have no
verified vendor-specific error bounds here.

For new PuD first-opening identities, preserve incoming Bank PREpb/AP/PB
recovery, PC PREab/AB/PB-spacing recovery, and **Bank conventional ACT→opening
nRC**. The last avoids opening PuD after early AP before the ordinary nRC
floor expires. This is an HBM3 binding requirement; it does not request
unrelated changes to completed DDR4/GDDR7 work.

The exact-half-CK precision alternative in §4 changes duration transport and
statistics, not the integer timing graph. It is a separately reviewed shared
consumer change, with HBM4 and other affected-standard regression scope.
Retaining 312 ps is a bounded approximation alternative, not an invisible fix.

### Generation, RFM and evaluation limits

[HBM34PerBankRefresh](../../../src/ramulator/controller/refresh/impl/hbm34_per_bank_refresh.cpp)
maintains one set per PC/Sid, enqueues a corresponding bank in each PC before
advancing its bank cursor, then advances Sid. It retries priority backpressure.
However, “refreshed” and final-set nRFCpb cooldown are recorded on successful
enqueue, not actual command issue. A delayed final refresh can therefore lose
the intended post-issue cooldown. The manager has no REFab-driven set reset.
Generic PerBank has neither HBM set tracking nor paired-PC coverage and
throws on enqueue failure; it is not an equivalent HBM34 policy.
AllBank emits one PC-wide REFab per PC every nREFI and throws on enqueue
failure. None proves a retention deadline under arbitrary prolonged PuD traffic.

JESD238 §6.3.2.6 describes complete per-SID REFpb sets with a final-command
cooldown. The observed enqueue-based manager cannot establish that contract
under backpressure. Issue-based bookkeeping, and reset handling if mixed
REFab generation is selected, are required before evaluating that policy.

| RFM property | HBM3 finding |
| --- | --- |
| Command existence | RFMab/RFMpb registered, row bus, one tick; refreshing metadata |
| Reachability | Manual priority injection and HBM34 pairing tests reach both identities; prerequisites use PREab/PREpb |
| Automatic generation | None in the inspected HBM34/REF managers; optional [RFMManager](../../../src/ramulator/controller/plugin/impl/rfm_manager.cpp) requires absent Rank |
| Conflict safety | Common target-bank protection is reusable; HBM3 PuD not implemented/tested; incoming and maintenance timing gaps above remain |
| Timing calibration | nRFMab=nRFC and nRFMpb=nRFCpb are aliases, not validated RFM latency |

A concrete bounded evaluation candidate uses the selected preset, exact
half-tick duration, the narrow edge/nRREFD repairs, Open row policy and
AllBank ordinary refresh, with canonical PC-wide scope. AP and manual REFpb
remain available for safety tests; automatic per-bank evaluation waits for
issue-based set tracking. No RFM-producing plugin/manager or manual RFM
workload is used in evaluation; traces must show zero RFM. Separate injected
RFM protection/recovery tests remain necessary. This retains command support
and ordinary refresh without claiming physical RFM timing or retention proof.
RFM traffic in a calibrated evaluation would require additional timing and
generation evidence, not merely passing injection tests.

Classification: core conventional PRE/ACT/read/write scopes are **already
adequate within their model**; representative geometry, direct preset values
and omitted PuD current/DQ paths are **bounded project approximations**;
the identified recovery gaps are **must repair before PuD**; physical
HBM3 array/PRADA/movement calibration, precise redundant-PRE/AP behavior,
vendor timing validation and RFM latency **require additional evidence**.
Automatic per-bank refresh has an additional must-repair condition before
that policy is evaluated. No blanket GDDR7 G6 repair is inherited.

## 8. Common substrate reuse and first consumers

Current [binding interface](../../../src/ramulator/dram/pud_binding.h),
[DDR4 binding file](../../../src/ramulator/dram/pud_binding_ddr4.cpp),
[GDDR7 binding](../../../src/ramulator/dram/pud_binding_gddr7.cpp), and
[placement implementation](../../../src/ramulator/dram/pud_location_ddr4.cpp)
were inspected against the current HEAD, not the pre-extraction audit snapshot.

| Boundary | Reuse or required change during separately authorized implementation |
| --- | --- |
| Request protocol, occurrence graphs, local phases and delayed completion | Reuse; no new engine or parent-operation machinery |
| BankIdentity, ExternalRow, LayoutRegion, paired projection and physical conflicts | Already vector-based through Bank; preserve all five HBM bank coordinates |
| Device flat-bank traversal, protected target enumeration and incoming timing checks | Already walk arbitrary hierarchy depth; no Channel→Bank assumption |
| Local Bank timing and occurrence delays | Reuse algorithm; supply HBM3 numeric edges, half-tick conversion and reception offsets |
| Dual command-resource accounting | Existing per-Device IDs suffice for two shared Channel buses; PC timing belongs in hierarchy publication |
| HBMControllerBase candidate/issue path | Already switches to common PuD path when capable; reuse rather than copy |
| HBM34 tick integration | Add common compute reservation call at the approved prologue point; it currently has none. Add ACT-like role recognition to pairing |
| Shared timing publication | New HBM3 binding must locate addressed PC and publish nPPD only, retaining local PRE recovery; copying GDDR7 root-only publication would incorrectly share PC timing |
| Placement construction/validation | Current constructor explicitly admits DDR4/GDDR7 and exact hierarchy alternatives; profile fields cannot yet describe HBM PC/Sid counts. Add approved HBM organization/profile checks |
| Scalar forward/inverse placement | Existing mixed-radix loops already use bank_sizes; reuse after constructor/profile generalization and independent PC/Sid bijection tests |
| Profile geometry/topology and standard declarations | New HBM3 profile and thin standard/binding registration required; no numeric DDR4/GDDR7 fallback |
| AllBank registration | Add the new standard's PseudoChannel scope to its name table if this policy is selected |
| Clock duration representation | Resolve exact-half-CK precision before G2 consumer; preserve conventional integer schedules and review shared reporting consumers |

There is genuinely common code in DDR4-named files:
`PuDBinding::command/local_timing/conventional_closed/conventional_drained`
and the multi-standard dispatcher live in `pud_binding_ddr4.cpp`.
The placement constructor, table validation and generic mixed-radix
forward/inverse map live beside DDR4 and GDDR7 factories in
`pud_location_ddr4.cpp`. Moving these shared definitions to common
implementation units while adding a third binding would isolate the actual
target factory/organization checks and avoid extending a DDR4-vs-GDDR7 branch
into implicit HBM behavior. This is a conditional implementation organization
change, not a filename-only cleanup or a new execution abstraction.

The actual blocker is the closed profile validation/schema, not loss of PC/Sid
in footprint identity. Legacy `ranks` and `rank_row_bits` names do not by
themselves impose Rank on execution; retain compatibility without assigning
Sid to those fields. All targeted primitives still require same Bank/subarray,
so the current protected-context assumption of one Bank remains valid.
G5/G7 parser, emitter and GEMV consumers were left outside this investigation.

## 9. Uncertainty and handoff boundary

The investigated model can support a representative architecture experiment,
but does not establish a physically implemented HBM3 PuD device. Modeling
status and implementation authorization belong to the
[canonical decision](../decisions/pud-multistandard-substrate.md#accepted--hbm3-g1g2g3g4g6-2026-09-17);
the candidates and alternatives here remain the investigation's technical record.
A silicon-fidelity claim would additionally require a part-specific
mat/subarray/datapath description, compatible PRADA measurements, internal
movement/command-encoding evidence and calibrated maintenance timings.
