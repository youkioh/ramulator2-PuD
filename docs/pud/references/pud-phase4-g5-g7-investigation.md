# Phase-4 G5/G7 trace and GEMV portability investigation

Investigation date: 2026-09-17. Branch: `feature/pud-multistandard-substrate`.
Source HEAD: `1072848f5c3360f12caa7921cca9fb4d3aabada5`; tree clean at initial entry.
The device/stack-scope continuation began with only these three investigation
documents uncommitted at the same HEAD.
Scope: G5/G7 research and documentation only. No production code, GEMV
execution, generated baseline or primitive evidence was changed.

This reference records code facts, derivations and investigated alternatives.
G5/G7 selections were accepted by the user on 2026-09-17; the canonical
decision owns their normative contracts. The descriptions below reflect those
selections while preserving alternatives as evidence, not live gates.
Phase-4 implementation remains unauthorized pending separate user approval.
The [canonical decision](../decisions/pud-multistandard-substrate.md) owns
acceptance; the [plan](../plans/pud-multistandard-substrate-plan.md#phase-4--reusable-operationgemv-integration-and-characterization)
owns implementation consumers. G0 and target G1/G2/G3/G4/G6 are fixed.
The complete [original audit](pud-multistandard-substrate-audit.md),
[GDDR7 reference](gddr7-pud-modeling-reference.md) and
[HBM3 reference](hbm3-pud-modeling-reference.md) were read. Their preimplementation
statements describe their recorded snapshots; current source and Phase-2/3
completion evidence establish that all three primitive bindings now exist.
The scope continuation cross-checks device/stack Channel counts against the
physical sources below. Accepted internal profile parameters are unchanged.

## 1. Current architecture and identity

Primary consumers inspected completely:
[PuDTrace](../../../src/ramulator/frontend/impl/memory_trace/pud_trace.cpp),
[GEMV generator](../../../tools/pud_gemv_generator/generator.py),
[functional replay and scalar graph](../../../tools/pud_gemv_generator/validation.py),
[runner](../../../experiments/pud_gemv_baseline.py),
[physical lowerer](../../../tools/pud_operation_generator/lowering.py),
[requirements](../../../tools/pud_operation_generator/requirements.py), and
[artifact writer](../../../tools/pud_operation_generator/artifacts.py).
The [GEMV contract](../decisions/pud-gemv-macro-contract.md) fixes arithmetic,
x duplication, both schedules and host completion semantics.

The actual executable path is:

```text
logical ADD/MUL and reduction schedule, output/domain/lane indices
 -> static output placement + designated local-row layout
 -> lower_to_physical: ordered local-row primitives
 -> physical request descriptions serialized as PuDTrace lines
 -> PuDTrace reader: resolver footprints -> paired operands -> C++ Request
 -> GenericDRAM explicit Channel routing -> controller PuD admission
 -> common occurrences, footprint protection, timing and terminal recovery
 -> completion callback -> next Request in that CHAIN
```

The Python generator emits strings, not C++ Requests. Thus C++ Request
construction occurs after trace reading, not before serialization.
The layout JSON is a generator/report/replay artifact; the frontend does not
read it. No scalar PA is required by this path.

| Layer | Information and authority |
| --- | --- |
| Logical/arithmetic | Six ADD/MUL builders; INT8 low-eight-bit exports and current FP8 graphs; logical A/x/products, reduction order and precision. No Bank hierarchy. |
| Target-independent mechanisms | Deterministic liveness allocation, primitive order/arity, inclusive MatRange, ordered Group positions, LC/GB occurrence graphs, CHAIN completion/retry protocol. |
| Target placement | Selected profile, Bank coordinates, Row subdivision, mat paths, groups, output slots and row bands. These determine which cells each logical lane occupies. |
| Trace/dependency metadata | Format version/profile assertion, level names/sizes; CHAIN ID; flattened completion indices and optional checkpoints. CHAIN expresses sequencing only, never target/engine/operation identity. |
| Physical execution identity | Retained resolver/profile/routing association plus complete BankIdentity, Subarray/LocalRow, physical chip/mat segments, and optional ordered Group. Row and Group identify data; conflicts intentionally protect whole mats and impose no-SALP separately. |
| Command observations | Issue clock, command, actual external address vector, Request type/source; a projection of execution, not a replayable mat-placement record. |

[Location types](../../../src/ramulator/dram/pud_location.h) already use variable
`BankIdentity` vectors; `LocationAssociation` carries `bank_levels/bank_sizes`.
[Region resolution](../../../src/ramulator/dram/pud_location.cpp) derives
Subarray/LocalRow from Row and pairs the canonical region with external
coordinates. Whole-row compute projects Column=-1; Group projects its inverse
burst selector. Explicit Column can be checked by the API but never narrows a
compute mat-row. Column, Group and mat-local cell column are different types.

[Request construction/conflicts](../../../src/ramulator/base/request.cpp),
[routing](../../../src/ramulator/memory_system/pud_request_routing.h),
[GenericDRAM](../../../src/ramulator/memory_system/impl/generic_dram_system.cpp)
and [controller validation](../../../src/ramulator/controller/pud_request_validation.cpp)
retain/check that association. PuD bypasses scalar channel/address mapping.
All operands must share a Bank/subarray; compute and LC share their range;
GB uses directed singleton neighbors in one participating chip/slice.
MAJ rows must be distinct. Public ingress rejects unlocated PuD.
GenericDRAM obtains the first controller's resolver; installed profiles require
one Channel. Variable vectors do not authorize multichannel execution. The
scope continuation below identifies the required routing/association extension.

PuDTrace parses the complete finite stream at setup. It preserves chain
first-appearance order, permits repeated CHAIN selections, holds at most one
outstanding Request per chain, attempts one ready-chain admission per frontend
tick, and rotates rejected chains to the back. Only the full completion
callback advances a chain. Empty chains/streams are allowed. Checkpoints are
one-based physical Request indices within selected chains; frontend and memory
clock ratios must match when collecting their timestamps. None of this needs
a target-specific scheduler. The Accepted per-controller admission budget
below changes the current global-one-attempt limit only during separately
authorized implementation.

### Trace and artifact inventory

| Format / reader-writer | Current representation and G5 relevance |
| --- | --- |
| PuDTrace physical input | Unversioned `PUD_TRACE / PROFILE <exact display name> / RANKS <count>`; CHAIN and seven opcodes. Four context integers, two mat integers, then rows or row/group pairs. This is the execution-input codec requiring extension. |
| GEMV layout JSON | Version 4; four-element output `context`, `ranks:1`, input/workspace/constant rows, domains, sink, residual count, counts and checkpoints. Writer/replay/runner own its interpretation; no independent JSON-schema validator exists in this path. |
| Operation artifacts | Symbolic manifest v1 and text/C++ fragments are not simulator ABIs. Physical-lowered JSON v2 has an explicit reader and local-row scope; default-layout JSON binds local rows; requirements JSON/header v1 derive counts. No Rank/Bank/PA is needed in these formats. |
| CHAIN latency CSV | Runner writes chain ID and acceptance/MUL/final-completion-derived cycle fields; no physical hierarchy. Keep its DDR4 bytes and meanings. |
| [CmdTraceRecorder](../../../src/ramulator/controller/plugin/impl/cmd_trace_recorder.cpp) | CSV header from DRAMSpec level names; legacy binary header has level/command counts and names. Both loop over actual level_count. Already preserve PC/Sid, but neither records MatRange, resolver association or CHAIN ID. All PuDTrace Requests currently have source_id=0. |
| [BinTraceRecorder](../../../src/ramulator/controller/plugin/impl/bin_trace_recorder.cpp), [live stream](../../../src/ramulator/controller/plugin/impl/live_trace_streamer.cpp), [viewer reader](../../../visualizer/app/composables/useTrace.ts) | Named levels/sizes and variable address arrays already common. RAM2BIN v1.2 carries fractional timing metadata; integer-duration targets retain v1.1. These are command-event formats, not substitutes for PuDTrace. |
| Other memory frontends | [ReadWriteTrace](../../../src/ramulator/frontend/impl/memory_trace/readwrite_trace.cpp) reads variable comma-separated ordinary coordinates; [LoadStoreTrace](../../../src/ramulator/frontend/impl/memory_trace/loadstore_trace.cpp) reads scalar LD/ST addresses. Neither constructs canonical PuD or CHAINs. |

A command trace alone cannot reconstruct full physical PuD identity, even when
its hierarchy is correct: compute has no Column and mat targets are absent.
G5 need not change these observational formats to encode execution input.

### Physical unit, controller instance and evaluation scope

These are three different scopes. A JEDEC Channel is an interface/resource
boundary; the number of Channels managed by a product called a memory
controller is not a universal JEDEC requirement. In this repository,
GenericDRAM deliberately assigns **one Channel per controller instance**.

| Target | Physical organization / evidence | Current instance | Evaluation unit selected by G5/G7 |
| --- | --- | --- | --- |
| DDR4 | Selected 64-bit non-ECC rank: eight x8 chips participating together | One GenericDDR + Device, one Channel, frozen rank count 1 | Existing one Channel/rank, eight chips; unchanged |
| GDDR7 | Selected x32 device: four independent x8 Channels | One GDDR7 + Device represents one x8 slice, 16 Banks, 512 MiB | Four instances, one GDDR7 x32 16-Gbit device: 64 Banks, 2 GiB |
| HBM3 | Selected complete stack: sixteen 64-bit Channels, each with two 32-bit PCs | One HBM34 + Device includes both PCs, 64 Banks, 512 MiB | Sixteen instances, 32 PCs, 1,024 Banks, 8 GiB |

Physical provenance: the [GDDR7 reference](gddr7-pud-modeling-reference.md)
already cites Micron's product brief, Table 1. Its
[current vendor asset](https://assets.micron.com/adobe/assets/urn%3Aaaid%3Aaem%3A087330f6-6d71-4575-b622-cb10f20cdaf0/original/as/gddr7-product-brief.pdf)
was rechecked through indexed PDF text: x32, four Channels/device, 16-Gbit
density, 32-byte access/Channel. Direct PDF retrieval was blocked during this
continuation. The [HBM3 reference](hbm3-pud-modeling-reference.md) identifies
JESD238; §§1–3.1.3 of the
[primary-standard transcription](https://studylib.net/doc/28350036/jesd238-hbm3)
state independent 64-bit Channels and two 32-bit PCs sharing each Channel's
row/column buses. It permits **up to** sixteen Channels and reduced-channel
devices; sixteen is the selected complete-stack scope, not a universal
requirement for every HBM3 device. The official JEDEC page was inaccessible;
the existing reference's third-party transcription is the provenance boundary.
Neither source establishes modeled mat wiring.

The DDR4 eight-chip construction is the Accepted
[placement model](../decisions/mimdram-addressing-geometry-and-payload.md)
and current factory: 8*8=64 data bits, 8*16=128 mats per external Bank/subarray.
The eight chips form one externally addressed Bank context; they do not create
eight command buses or eight additional external Bank indices.

The [GDDR7 preset](../../../python/ramulator/dram/gddr7.py) has density=4096 Mb,
16 Banks, 16384 rows, 2048 columns, DQ=8: 512 MiB per slice, one quarter of
the named 16-Gbit component. The
[HBM3 preset](../../../python/ramulator/dram/hbm3.py) gives
2 PCs * 2 Sids * 4 BG * 4 Banks * 8192 rows * 256 columns * 32 bits
= 4 Gibit = 512 MiB per Channel. Sixteen copies give 64 Gibit = 8 GiB,
arithmetically consistent with eight 8-Gbit dies in `HBM3_8Gb_8hi`.
This checks selected capacity, not a vendor die-to-Sid wiring map. Sid has
already contributed a factor of two; neither stack height nor `chips=1`
is an additional capacity multiplier. HBM's width field denotes an accessed
32-bit PC slice; both PCs are already in the Bank ancestry.

### DDR4 eight-path source audit

`_output_placement` consumes Bank, BG, range slot, **chip**, subarray and row
band, in that order. With K mats/output, q=floor(16/K), output index
`16*q*chip` reaches mat `16*chip` in Bank 0, subarray 0, band 0.
Thus all eight paths are available; domain extent uses
`mats_per_chip=16`, never `logical_mats=128`. The capacity factor C_s=8
counts these paths, not controller replicas.

Read-only probes enumerated every first-subarray/first-band slot for K=1,2,16:
2,048 / 1,024 / 128 placements, respectively, all eight chip IDs and no duplicate
Bank/range placement. First mats are 0,16,32,48,64,80,96,112.
The successor factory ends every path at 15,31,...,127. Generator `move()`
checks that relation, so a GB 15->16 edge is rejected. Layout metadata carries
global logical mat indices; the writer preserves them; replay keys cells by
`(*context, mat)` and does not truncate to the first chip. In-memory replay
of both schedules at N=528, rebased onto the legal chip-7 placement (mats 112–113),
matched the current INT8 scalar graph.

Resolver segmentation converts each logical mat to chip=mat/16 and local
mat=mat%16. Compute and LC may legally span chip boundaries; their semantics
are parallel per-mat work, not a GB link. Probes checked ranges 15..16, 0..127
and 112..127. GEMV's connected output ranges deliberately stay within one path.
PuDTrace passes endpoints to this resolver without clamping to16; controller
footprint validation retains the resolved segments. No hidden single-chip
restriction was found in this path. All chip placements still use Channel 0,
the same sixteen external Banks, and GenericDDR's one shared command bus.

## 2. Fixed assumptions and first consumers

| Current assumption | Exact consumer / consequence |
| --- | --- |
| Exactly four Bank-context integers | PuDTrace uses values[0..3], mats[4..5], operands from 6; movement requires ten integers. GDDR7 needs two Bank coordinates, HBM3 five. Merely changing PROFILE/RANKS cannot work. |
| DDR4 profile only in production Python export | [bindings.cpp](../../../src/ramulator/python/bindings.cpp) no-argument `pud_placement_profile()` calls the DDR4 factory and omits association bank_levels/bank_sizes and target selection. C++ already has three factories. |
| Rank 0/Channel 0 and BG/Bank divisors | `_output_placement` returns [0,0,bg,bank], uses bank_groups/banks_per_group, and rejects beyond one-rank capacity. `rank_counts` export does not make GEMV multirank. |
| Chip-local domain and range packing | Generator uses mats_per_chip for maximum domain and range; assumes uniform chip/slice paths, checks every successor. This is valid for all three Accepted linear profiles, not a general graph placer. |
| Profile H and contiguous ordered group layout | N/offset/count must be divisible by the profile's H; group selector is offset/H. Replay uses group_position_to_column. All three Accepted maps are identity; arbitrary nonidentity layouts need separate validation, not an inferred permutation policy. |
| DDR4-shaped output serialization | Layout v4 `ranks:1`; trace writer emits RANKS; replay destructures ch/rank/bg/bank; runner zips four fixed labels. Both CLIs expose arithmetic baseline/format, no target parameter. |
| DDR4 run configuration | Runner selects DDR4_PuD_Movement, GenericDDR, rank 1, H=4, fixed profile, FRFCFS/Open/NoRefresh, PuD buffer 32, one Channel, ratios 1. Counts every recorded command as a completed PuD occurrence. |
| Geometry-dependent experiment bound | Runner rejects N > width*mats_per_chip before generation because the PuD in-memory phase latency experiment requires D=1. General generator supports multiple domains. |
| DDR4 fixture offsets | GEMV/frontend tests read fields[4..6], skip exactly three header lines, expect six command coordinates, H=4, 1024-row subdivision, 16-Bank/8-chip/16-mat enumeration. Preserve these as legacy tests; add new-target coverage separately. |
| Local-row default 1024 | Physical lowerer's default helper and requirement derivation use 1024. Actual GEMV lowering already passes rows_per_subarray explicitly. Requirements are logical allocation counts; probe below confirms all six operations fit 512 without changing allocation. |
| Remaining compatibility names | `rank_row_bits` is logical_mats*cells_per_mat_row on every target; association.ranks is 0 for rankless targets. Neither is execution Rank identity. Do not serialize RANKS 0 as an invented level. |
| Test-only DDR4 helpers | `region_cell` in [location harness](../../../tests/utils/pud_location_harness.h) constructs four zero Bank coordinates; `info.chip_capacity_bits` multiplies BG*Bank and omits PC/Sid, giving 0 for GDDR7 and incomplete HBM capacity. Use resolver.capacity_bytes and actual ancestry products instead. |
| Viewer naming fallback | [traceTree.ts](../../../visualizer/app/utils/traceTree.ts) rankLevelIndex falls back to index 1; bankGroupLevelIndex also has DDR-style fallbacks. Variable arrays preserve identity, but these presentation helpers are not topology/resource authority. No viewer refactor is required for PuDTrace integration. |

Target-specific Rank timing in DDR4 and PC/Sid/BG pairing in HBM34 are legitimate
binding behavior, not common-code defects. The profile constructor explicitly
checks all three exact supported hierarchies. Legacy unlocated DDR4 movement
diagnostics retain 128/16 constants but public canonical ingress rejects that
fallback. Existing examples and DDR4-only harness assertions need not become
new-target APIs. Common Device flat-bank traversal, Request conflicts and
controller validation already walk actual hierarchy depth.

### Multi-Channel execution: current blockers and selected architecture

The complete [GenericDRAM construction/send/tick path](../../../src/ramulator/memory_system/impl/generic_dram_system.cpp)
creates a controller list, assigns IDs 0..N-1, and ticks every controller.
Each controller owns its own Device, queues, arbitration, timing state,
refresh manager and binding. Conventional four-Channel GDDR7 configuration
already has a test; read-only production construction also succeeds with
sixteen HBM34 instances when canonical PuD profiles are not installed.

The single-Channel restriction is in canonical placement integration:

1. Each target controller calls its binding's `placement()` during child
   initialization with `MappingContext.channels=1`. Each call creates a
   distinct immutable resolver/association.
2. The resolver constructor requires context.channels=1 and local DRAMSpec
   Channel size1, copies that size into bank_sizes, and its scalar mapper
   leaves BankIdentity[0]=0. Explicit Channel 1 is out of bounds.
3. GenericDRAM checks every installed association's Channel count against N.
   Four/sixteen installed profiles fail immediately with
   `memory-system routing disagrees with location profile`.
4. GenericDRAM exposes controller 0's resolver and checks association **identity**,
   not merely equal profile data. Even deleting the count guard would reject
   controller 1's separately constructed association or pass the wrong one.
5. ControllerBase validates routing count, association identity and full
   placement, and requires operand Channel==its controller ID. PuDTrace only
   knows the single resolver returned by the memory system.

A crucial source detail rules out blindly rewriting every request Channel to 0:
[ControllerBase::set_channel_id](../../../src/ramulator/controller/controller_base.cpp)
also calls [Device::set_channel_id](../../../src/ramulator/dram/device.cpp),
which relabels the **single root node to the global ID**. Local DRAMSpec
Channel size1 means one root in that Device, not that its runtime ID must be 0.
Node matching, maintenance address construction and command records use that
global ID. Lower-level Bank indexing is local to the Device. Global Channel
coordinates are already the normal execution convention.

| Architecture alternative | Assessment |
| --- | --- |
| One shared system-scoped resolver/association over homogeneous Channel instances | Selected by G5: retains global BankIdentity end to end, preserves pointer-identity checks and existing Device root labels, avoids request re-resolution on retry/callback. Profile geometry and each Device tree remain per Channel. |
| Local Channel0 resolvers plus a global routing wrapper | Possible with a rigorously paired global/local identity boundary, but not a drop-in wrapper: current controller and Device validation expect global IDs, and immutable paired projections forbid editing only operand[0]. Requires rebasing associations/regions and preserving callback identity, or separate controller-scoped global-ID views. More transport states to verify. |
| One synthetic device-wide GDDR7/HBM34 controller | Unnecessary and contrary to existing construction: would merge independent queues/buses/timing state and require a new controller resource model. |
| Remove checks / inflate DRAMSpec Channel count only | Incorrect: does not repair association identity, scalar origin mapping or root construction. |

**Selected architecture, not implemented:** initialize a homogeneous system
association after N and controller IDs are known, before traffic/frontend setup.
MappingContext.channels=N and association.bank_sizes[0]=N; the remaining sizes
come unchanged from the validated local profile. Share the same immutable
resolver/association with all participating controllers and system ingress.
Validate each local DRAMSpec with Channel size1, plus system count/profile/
organization/mapper equality separately. Do not construct N roots inside each
Device. Existing install-once checks mean initialization sequencing must change;
do not mutate an installed association or relax foreign-association rejection.

A parsed Bank vector stays global in Request origins, paired projections,
footprints, controller submission and command observations. GenericDRAM checks
all operands' Channel, selects controller[c], and that controller validates c
against its global root ID. Cross-Channel operands remain illegal. The facade
needs no Device/Stack coordinate, CHAIN metadata or scalar address for PuD.
The selected scope is homogeneous 1/4/16 instances of the selected target;
heterogeneous profiles/clock domains within one trace are not inferred.

Scalar compatibility must not become an accidental hole in this extension.
The current forward/inverse resolver skips the Channel dimension, while
ordinary admission checks original global req.addr. Simply enlarging bounds
would alias Channels. For ordinary coexistence, the selected transport
extension composes the existing CacheLineInterleave (default interleave_bits=0)
with unchanged local RoBaRaCoCh; it does not choose a new GPU PA map.
For burst bytes t, byte a yields c=floor(a/t)%N and local byte
`t*floor(a/(t*N))+a%t`; inverse inserts c at that same position.
Use local profile mapping on that compact byte, retaining global c in identity.
Validate the actual interleave parameter, which MappingContext currently
does not record; reject unsupported settings. Preserve all N=1 scalar results.
The Accepted per-Channel G1 geometry/mapping and primitive evidence remain
unchanged; aggregation is the Accepted G5 routing integration, not new physical
wiring. Explicit PuD must continue bypassing scalar execution.

CHAIN already tracks callbacks by chain, not controller. One chain can
sequence otherwise legal Requests to different controllers without acquiring
new target semantics; G7 nevertheless keeps each output on one Channel.
Rejected sends retain the same immutable Request; full recovery callbacks
advance it exactly once. GenericDRAM's sequential controller tick loop gives
deterministic callback ordering at equal ticks. New tests must cover retries,
foreign associations, wrong roots, cross-Channel rejection and chain completion
across controllers; none of those end-to-end PuD cases works today.

## 3. G5 representation candidates

The current physical input already has the necessary **kinds** of structured
location: Bank context, explicit Row, MatRange and Group. Its serialized grammar
and Python consumers fix DDR4 widths and Rank metadata. Thus a small versioned
schema extension is necessary. The existing location types remain suitable,
but their system association/validation must gain global Channel scope as above.

| Shape | Trade-off |
| --- | --- |
| A. Named variable Bank vector | One common grammar; exact PC/Sid retention; directly matches LocationAssociation. Names/counts are asserted once per trace, not repeated per operand. Selected representation below; acceptance is recorded in the canonical decision. |
| B. Standard/profile plus fixed target fields | Can represent identity if each target gets a separate field branch, but duplicates parser/JSON cases and encourages dummy nullable Rank/PC fields. Provides no capability missing from A. |
| C. Profile-inferred variable vector | Smallest byte header: version+profile, with depth/names inferred entirely from installed resolver. Feasible for current immutable profiles, but less self-describing and still needs organization replication checks. Existing named-vector association makes A a small, explicit extension. |
| Reuse command CSV/RAM2BIN | Not sufficient: lacks mat/group regions, operand pairing and dependencies. Adding those would be a larger new ABI. |
| Per-operand named JSON locations | Expressive but repeats same Bank context and permits shapes current same-Bank primitives reject. Unnecessary for these seven operations. |

### Selected representation and compatibility analysis

Retain legacy DDR4 output unchanged. Add a new format for new targets:

```text
PUD_TRACE 2
PROFILE MIMDRAM-HBM3_8Gb_8hi modeled placement profile v1
BANK_LEVELS Channel PseudoChannel Sid BankGroup Bank
BANK_SIZES 16 2 2 4 4
CHAIN 0
RowCopy 7 1 1 3 2 0 1 10 11
LC-MOV 7 1 1 3 2 0 1 11 0 12 1
GB-MOV 7 1 1 3 2 0 1 12 1 13 2
```

Here RowCopy/LC select mats 0..1; GB selects source mat 0 and destination mat 1.
Every line's global Bank is [7,1,1,3,2], routed to HBM34 controller7.
GDDR7 device traces declare
`BANK_LEVELS Channel Bank / BANK_SIZES 4 16`, with two context integers.
DDR4 can be represented by the same v2 grammar with four coordinates, but
existing DDR4 generation would continue emitting the legacy format.

For depth L, records are:

```text
compute: opcode bank[0..L-1] first_mat last_mat row...
LC-MOV:  opcode bank[0..L-1] first_mat last_mat src_row src_group dst_row dst_group
GB-MOV:  opcode bank[0..L-1] src_mat   dst_mat  src_row src_group dst_row dst_group
```

Rows are external Bank row IDs. Subarray/local row are profile-derived,
not additional hierarchy levels. Shared Bank context is sufficient because
all Accepted primitive endpoints must share it; separate endpoint Row/Group
and GB mat fields retain their full differing identities. Cross-Bank endpoints
are not silently made legal by v2.

- PROFILE is the exact existing display name, distinct from controller config
  aliases such as `MIMDRAM_HBM3_8Gb_8hi_v1`. An installed, validated resolver
  supplies execution authority. An additional STANDARD or timing-preset field
  is unnecessary for physical identity: profile plus exact levels/sizes is
  checked against that authority. Results/configuration still identify
  standard, organization and timing explicitly.
- BANK_SIZES replaces DDR4-specific replication metadata with a common
  **global system** organization assertion: 1/1/4/4 for frozen DDR4,
  4/16 for GDDR7, 16/2/2/4/4 for HBM3. Assert Channel count against the actual
  controller list and other sizes against every local profile. A separate
  CHANNELS assertion with BANK_SIZES starting at 1 is possible, but would
  describe bounds that disagree with the serialized coordinates and duplicate
  authority. G5 selects global sizes. No extra Device/Stack level is needed.
- No Column input. Compute has absent Group and projects Column=-1; movement
  carries Group and derives burst Column through the profile's inverse table.
- FULL_MAT remains a construction-only tag: serialize resolved
  `0 logical_mats-1` (DDR4 0..127, GDDR7 0..31, HBM3 0..15).
  An explicit identical range is equivalent; no wildcard/negative sentinel
  or distinct execution meaning is introduced.
- One common layout v5 for new targets would retain output `context` vectors
  and existing row/domain records, add global top-level bank_levels/bank_sizes, and
  omit ranks. Existing DDR4 layout v4, key order, whitespace, fields and values
  remain byte-identical. Version-aware replay normalizes both to the same
  internal location shape. No new local-row/requirements schema is needed.

### Validation and compatibility boundary

The v2 parser would require a supported version, exact installed profile,
unique ordered level names exactly matching the resolver's prefix through Bank,
positive matching global sizes and equal name/size lengths. Validate the
system association against all N local Channel-size1 instances before accepting
the header; a one-Channel installation must reject device/stack counts. Do not accept inferred
aliases, reordered names, omitted PC/Sid, synthetic levels or arbitrary depth.
Consume exactly L context fields; movement requires L+6 integers, compute
L+2 plus its validated operand arity (RowCopy at least 2; MAJ3=3, MAJ5=5,
NOT=1, NOT_COPY=2). Require in-range integer parsing, nonnegative coordinates,
valid Rows/Groups and ordered inclusive ranges. Reject unsupported tokens and
extra fields for fixed-arity operations.

Canonical resolver and Request validation remain authoritative for complete
external projection length L+2, bounds, same Bank/subarray, whole-row versus
group scope, equal LC/compute ranges, distinct majority rows and directed
singleton GB topology. No scalar resolution is added to frontend ingress.
CHAIN/checkpoint rules, callback timing, fairness and source IDs remain unchanged.

Legacy unversioned input continues its existing PROFILE/RANKS and four-context
interpretation on DDR4; it must not be guessed as rankless input. Old binaries
reject v2 by their existing exact magic check, rather than misexecute it.
A new reader accepts legacy DDR4 and v2; writers select legacy DDR4 by default.
New-target metadata must not be appended to frozen DDR4 JSON/traces/CSVs.
This preserves byte/content identity, not merely normalized semantic equality.

## 4. Cross-target geometry, resources and capacities

Values below come from current
[profile factories/validation](../../../src/ramulator/dram/pud_location_ddr4.cpp)
and Accepted target authority. The original table and capacities are explicitly
**per controller Channel**, not per GDDR7 device or HBM3 stack. They describe
modeled profiles, not measured target wiring. DDR4 here means its frozen
one-rank GEMV configuration. Aggregate evaluation values follow below.

| Property | DDR4 | GDDR7 | HBM3 |
| --- | --- | --- | --- |
| Hierarchy through Bank | Channel/Rank/BG/Bank | Channel/Bank | Channel/PC/Sid/BG/Bank |
| Local Bank-coordinate sizes | 1/1/4/4 | 1/16 | 1/2/2/4/4 |
| Rows/Bank; rows/subarray; subarrays/Bank | 65536; 1024; 64 | 16384; 512; 32 | 8192; 512; 16 |
| Mats/subarray | 128 = 8 chips * 16 | 32, one x8 slice | 16, one logical 32-bit slice |
| Cells/mat-row; HFF-equivalent H; groups | 512; 4; 128 | 512; 8; 64 | 512; 16; 32 |
| Bank row size; Channel capacity | 8 KiB; 8 GiB | 2 KiB; 512 MiB | 1 KiB; 512 MiB |
| Banks/controller Channel | 16 (64 with separately configured 4 ranks, outside current GEMV) | 16 | 64: 32/PC, 16/Sid/PC |
| Legal GB topology | Eight separate 16-mat forward paths; no chip crossing | One 32-mat forward path | One 16-mat forward path per Bank; no PC/Sid crossing |
| Connected reduction extent | 8192 elements | 16384 elements | 8192 elements |
| No-SALP consequence | Different subarrays in the same Bank serialize through recovery | Same | Same, with full PC/Sid Bank identity |
| Controller resources, separate from geometry | One shared CA bus; 833 ps/CK | Shared Channel row/column buses; 571 ps/CK4; RCK column contention | Shared Channel row/column buses; 312.5 ps/half-CK, edge pairing, PC-local PRE spacing |
| Target G7 constraints | Preserve rank 0 ordering, 8 disconnected chip paths and H=4 | Whole groups of 8; no Rank/BG; 512-row budget | Whole groups of 16; preserve PC/Sid; 512-row budget; PCs do not have independent CA buses |

**Geometry is storage capacity.** **Controller concurrency** additionally
depends on footprints, no-SALP, queue sizes, command resources, timing,
maintenance and CHAIN readiness. There is no finite engine limit.
**GEMV placement policy** chooses which Bank/path/range/band gets each output;
none of the profile numbers determines an optimal order.

For the selected uniform placement, let W=512, P=path mats, C_s=participating
chips/slices, B=Bank count, S=subarrays/Bank, R=rows/subarray. Existing arithmetic
has w=8 result rows and C=2 union constant rows. Let T be the maximum ADD/MUL
temporary-row requirement and K=ceil(min(N,W*P)/W).
**D is the number of domains belonging to one GEMV output**, with
D=ceil(N/(W*P)). A domain partitions that output's dot product; it is not an
independent output.

```text
F = 2*w*D + 3*w + C + T
q = floor(P/K)
bands = floor(R/F)
M_capacity_per_Channel = B*S*C_s*q*bands
M_capacity_evaluation = channels * M_capacity_per_Channel
```

This is the existing reservation policy applied to the selected target
profiles, not maximum possible packing. Reject F>R or M>M_capacity_evaluation before
lowering; unused path tails and unused row-band tails stay unused.

Read-only derivation from the actual six lowered programs:

| Format | ADD/MUL temporary rows | ADD/MUL primitive counts | F when D=1 | DDR4 bands | GDDR7/HBM3 bands |
| --- | --- | --- | ---: | ---: | ---: |
| INT8 | 6/18 | 46/612 | 60 | 17 | 8 |
| FP8-E4M3 | 22/12 | 1331/318 | 64 | 16 | 8 |
| FP8-E5M2 | 17/7 | 1045/326 | 59 | 17 | 8 |

All six operations were lowered successfully with an explicit 512-row layout:
standalone total footprints 31/44, 48/38, 43/33 rows respectively. These are
operation footprints, not whole-output F; no row allocator redesign is needed.

| Output capacity per Channel when D=1 | DDR4 INT8/E4M3/E5M2 | GDDR7, all formats | HBM3, all formats |
| --- | --- | ---: | ---: |
| K=1 | 2,228,224 / 2,097,152 / 2,228,224 | 131,072 | 131,072 |
| K=whole path (16/32/16) | 139,264 / 131,072 / 139,264 | 4,096 | 8,192 |

For arbitrary K, use the formula; both schedules have identical placement
capacity. Each additional domain adds 16 rows. All three formats allow at most
61 domains on DDR4, 29 on GDDR7/HBM3 under this unchanged allocation:
conditional N maxima 499,712, 475,136, 237,568, respectively. These are per-output
storage bounds, not the runner's D=1 limit or throughput claims.

### Aggregate scope without enlarged reduction domains

The selected Channel factor multiplies independent output slots, **not** P,
H, K, F, mats/Bank, or the connected extent of one reduction. Both schedules have
the same storage capacity. Each output stays in one Channel/Bank/subarray.

| Quantity | DDR4 evaluation (1 Channel) | GDDR7 per Channel / device (4) | HBM3 per Channel / stack (16) |
| --- | ---: | ---: | ---: |
| Capacity | 8 GiB | 512 MiB / 2 GiB | 512 MiB / 8 GiB |
| External Banks | 16 | 16 / 64 | 64 / 1,024 |
| PCs | N/A | N/A | 2 / 32 |
| Independent controller instances / command-resource sets | 1 | 1 / 4 | 1 / 16 |
| Connected paths per Bank/subarray | 8 | 1 / 1 | 1 / 1 |
| Full paths over all Banks/subarrays, before row bands | 8,192 | 512 / 2,048 | 1,024 / 16,384 |
| K=1 range slots before row bands | 131,072 | 16,384 / 65,536 | 16,384 / 262,144 |
| Full-path output capacity when D=1: INT8 | 139,264 | 4,096 / 16,384 | 8,192 / 131,072 |
| Full-path output capacity when D=1: E4M3 | 131,072 | 4,096 / 16,384 | 8,192 / 131,072 |
| Full-path output capacity when D=1: E5M2 | 139,264 | 4,096 / 16,384 | 8,192 / 131,072 |
| K=1 output capacity when D=1: INT8/E4M3/E5M2 | 2,228,224 / 2,097,152 / 2,228,224 | 131,072 each / 524,288 each | 131,072 each / 2,097,152 each |
| Elements/domain from the connected path, unchanged | 8,192 | 16,384 | 8,192 |

Full paths count `channels*B*S*C_s`; K-mat slots count that value times
floor(P/K); row bands then multiply storage capacity. Different subarrays in
one Bank still cannot execute concurrently. These are not simultaneous
invocation counts or predicted speedups.

With 32 PuD queue entries per controller, aggregate queue space would be
32/128/512 entries; no global finite engine pool follows. Independent command
interfaces can progress in parallel, subject to each target's unchanged local
timing and maintenance. Current PuDTrace code attempts at most one Request
per frontend tick across the whole system. Accepted G5 changes that budget to
**at most one ready Request admission attempt per controller per frontend
tick**: up to 1/4/16 attempts for DDR4/GDDR7/HBM3. Static placement selects the
destination; this does not add dynamic load balancing. Preserve existing
CHAIN ordering, one outstanding Request per chain, retry semantics and
deterministic arbitration among ready chains targeting the same controller.
A rejected attempt consumes that controller's tick budget; admission on other
controllers can still proceed. Small M, startup and dependencies can still
underfill controllers. The accepted rule is not implemented by this document.
Identical clock presets and one GenericDRAM clock ratio keep this evaluation
synchronous, even though physical
Channels need not be synchronous. No linear speedup is claimed.

## 5. G7 logical placement interface

A small common interface can separate logical schedule inputs from physical
coordinates without creating a compiler/runtime optimizer:

```text
logical input:
  baseline + arithmetic format + M,N
  output index, domain index, operand/workspace role, bit plane, logical lane
target description:
  validated profile/association, real bank_levels/bank_sizes
  row extent/subdivision, mat segments and directed successors
  cells/mat-row, H, ordered group-position map
placement result:
  Bank vector, subarray, local row band, ordered reserved MatRange
  domain term intervals, A/x rows, private workspace/constants/temporary rows
  sink Mat + result rows + residual count + completion checkpoint
lowering:
  External Row = subarray*rows_per_subarray + designated local row
  compute -> Bank + Row + MatRange
  movement -> same Bank + endpoint Row + MatRange/singleton + Group
```

A logical lane j within a domain maps to its selected mat at floor(j/W),
and ordered position j%W; Group=floor((j%W)/H), position=(j%W)%H.
The profile maps that ordered position to the cell column. No byte address,
new hierarchy level, synthetic chip, or Rank synonym participates.
Use the C++ profile/association export as the sole geometry authority;
do not reconstruct new-target geometry from DDR4's dictionary fields.

**Selected traversal**, fastest to slowest, uses the strongest independent
command-resource boundary first on new targets. It is static output striping,
not dynamic load balancing or a runtime scheduler.

| Target | Enumeration selected by G7 |
| --- | --- |
| DDR4 | Existing Bank -> BG, Channel0/rank0 fixed; range slot -> chip -> subarray -> band. Preserve exact frozen order. |
| GDDR7 x32 device | Channel -> Bank -> range slot -> subarray -> row band. One slice per Bank. |
| HBM3 stack | Channel -> PseudoChannel -> BankGroup -> Bank -> Sid -> range slot -> subarray -> row band. One slice per Bank. |

For GDDR7, outputs0..3 are [c,0], output4=[0,1], and output63=[3,15].
For HBM3, outputs0..15 are [c,0,0,0,0], output16=[0,1,0,0,0],
output32=[0,0,0,1,0], output128=[0,0,0,0,1], output512=[0,0,1,0,0],
and output1023=[15,1,1,3,3]. Only then advance the range slot.

Investigated alternatives: Channel-first exposes independent interfaces before
Bank-first within one Channel; HBM PseudoChannel striping next exposes PC-local
PRE/maintenance resources. PCs still share their Channel's buses. The previous
HBM proposal put Bank before BankGroup; the user's Accepted order instead puts
BankGroup before Bank. This is the selected deterministic maximum-parallelism
baseline, not a claim of global optimality. The alternatives are retained as
investigation context, not unresolved placement gates. Ordinary PA low-bit
order does not dictate explicit output placement.

Every global Bank consumes a range slot before any consumes the next range.
Ranges remain low-to-high nonoverlapping K-mat paths; verify successor edges,
never cross chip/slice boundaries. Reserve maximum K across an output's
domains; later smaller domains use the prefix. No Channel multiplier appears
in connected path length or a primitive MatRange.

Both schedules keep all domains of one output in one Channel/Bank/subarray/range and
one chain. A/domain d and duplicated x/domain d each occupy w distinct bit rows,
followed by primary/reduction/movement workspaces, constants, then T temporary
rows. Row numbers on disjoint mats are distinct storage. All inputs are
preplaced; generator trace contains no host upload or x-duplication commands.

`x_duplicated[i][j]=x[j]` remains logical duplication per output. Each x fragment
is colocated with the corresponding A fragment in the same Bank/subarray/mat
and ordered lanes, in separate input rows. It is not shared between output
chains or distributed using an invented cross-Bank copy.

### Reduction order and target dependence

The common schedule algorithms and existing ADD/MUL primitive sequences can
remain single implementations. Their loop extents depend on the profile:
H determines group alignment/local stopping point, and the connected path
determines domain extent. Therefore **identical cross-target physical
Request sequences or FP8 results do not follow** from common algorithms.

Profile H=8/16 prevents the existing position-preserving movement from reducing
below 8/16 residual lanes. Reproducing the DDR4 four-lane endpoint would require
a new cross-position shuffle/masking mechanism or a different graph, neither
authorized. GDDR7's 32-mat path also permits a 16384-element domain versus
DDR4/HBM3's 8192. A deliberate 16-mat cap was an investigated alternative;
it would make FP8 domain grouping closer to DDR4 but waste legal connected
extent and still could not remove the H difference. It was not selected.

The selected design instantiates the **same existing schedule definitions**
with the target profile's H and connected path: H=4/8/16 and 16/32/16 mats
for DDR4/GDDR7/HBM3. Arithmetic/precision, x duplication and host
residual/domain order remain unchanged. Cross-target FP8 bit-exact equality
is not claimed because reduction grouping depends on H and connected-path
geometry. INT8 semantics remain unchanged. No padding, shuffle or arithmetic
redesign is selected.

## 6. Both schedules on the three targets

Placement unit for both is one output's K-mat reservation plus its complete
row band in one Bank/subarray. Arithmetic works over whole mat rows without
an active-lane mask; metadata and the existing suffix-preservation graph keep
invalid tail values out of readout.

**InterMatFirst:** ranged MUL on each domain's participating prefix; forward
fold from lowest to highest mat. At each edge transfer W values through GB
(bit-plane then group order), ADD the destination's primary products to the
incoming accumulator, and for a partial final destination restore the moved
valid suffix with LC. Then run the existing local tree at the sink. With K=1,
reduce only the valid element count; with K>1 the sink accumulator has W valid
folded positions. No new Bank/subarray movement occurs.

**IntraMatFirst:** ranged MUL; run the same local tree on all full mats as one
range within this output; separately reduce a partial last mat without padding.
Forward only H residuals through each GB edge, adding destination-local
residuals as the left operand and incoming accumulator as the right operand.
No second sink tree. Full-mat range LC means separate local copies on each
selected mat, not inter-mat transport.

| Schedule consequence, w=8 and a full mat | DDR4 | GDDR7 | HBM3 |
| --- | ---: | ---: | ---: |
| Maximum mats/domain | 16 | 32 | 16 |
| InterMatFirst GB Requests per edge (w*W/H) | 1024 | 512 | 256 |
| Full local tree ADD stages, log2(W/H) | 7 | 6 | 5 |
| Full local tree LC Requests, w*(W/H-1) | 1016 | 504 | 248 |
| IntraMatFirst GB Requests per edge (w) | 8 | 8 | 8 |
| Residual lanes/domain for host | 4 | 8 | 16 |

The ranged local-tree LC count is per identical full-mat range, not multiplied
by range width; moved bits do scale with width. Partial-final-mat repair and
non-power-of-two prefolding add their existing operations. These are derived
counts for the selected geometry, not executed new-target GEMV baselines.

For a valid local count v that is not a power of two, let
t=2^floor(log2(v)), e=v-t. The existing graph moves the e high terms to the
movement workspace, ADDs them into the low e lanes, preserves lanes[e,t)
with LC, then halves until H. Since W and the profile's H are powers of two and
N is H-aligned, all extents/offsets remain whole groups. N need not be a power
of two or multiple of 512: 24 works for GDDR7; 48 for HBM3; common N=528 gives
a full mat plus 16 valid lanes on every target. N=12 and 516 remain supported
DDR4 cases but are rejected on both new targets under the profile's H alignment.
There is no padding, partial-group movement or new host tail fallback.

LC is legal for equal nonempty source/destination mat ranges, common endpoint
rows/groups per range and the same Bank/subarray. GB is legal only for a
profile-directed singleton pair in one chip/slice and the same Bank/subarray;
source/destination groups may differ with ordered-position correspondence.
The generator uses LC for within-mat shifts/suffix copies and GB for forward
neighbor folds. It does not emulate reverse, wrap, disconnected-chip,
cross-subarray or cross-Bank transfers.

### Spanning capacity and host boundary

Multiple outputs follow the selected Channel/Bank order, then disjoint ranges, then
subarrays and finally disjoint row bands. Different Banks can overlap subject
to shared resources. Different subarrays in one Bank serialize even with
disjoint mats; row-band reuse on the same mats also conflicts. Neither storage
fallback nor PC/Sid enumeration creates SALP or an engine pool.

A long single output uses sequential domains, each with distinct preplaced A/x
rows and reused workspaces on its original reservation. It does not spread
domains across Banks/subarrays to escape F>R. Excess F or total M fails early.
Allowing such spreading would be a new placement/liveness/completion policy,
outside the Accepted placement scope.

At each domain completion, the existing external host/replay boundary reads
the sink's H residual lanes in ascending lane order, starts a domain sum at
zero, and then accumulates domain sums in ascending domain order. Results must
be observed before the next domain overwrites the reused workspace. The
functional replay snapshots at completion_index; Ramulator has no payload
readout or host timing/join implementation. Final y is a host result, not a
new designated DRAM row. General generation supports D domains/output; the PuD in-memory phase latency
runner retains its explicit D=1 bound.

Report residual lanes/output separately from PuD cycles: for D domains the
host consumes D*H values/output (H=4/8/16). The current zero-initialized scalar
graph performs D*H residual-fold ADD calls plus D domain-accumulation ADD calls,
or D*(H+1) host ADD calls/output; multiply by M for workload totals. For the
D=1 runner this is 5/9/17 calls/output, including its explicit zero
seeds. Do not silently report the reduced H-1 mathematical addition count as
that graph's work. Report **PuD in-memory phase latency**: timing ends at PuD
residual completion, including terminal recovery. Host residual readout/folding
and inter-domain accumulation remain outside the timing model; this is not
end-to-end GEMV latency. Preserve defined INT8 semantics; cross-target FP8
bit-exact equality is not claimed under profile-dependent reduction grouping.

## 7. Runner and genuinely target-specific inputs

Keep one generation/replay/runner mechanism with separately selected target
configuration and format version. Genuine differences are profile hierarchy,
row/mat/group bounds and topology, actual controller/DRAM registration,
timing calibration, command buses/edge rules, maintenance policy and physical
time units. All are data/binding inputs; they do not require three arithmetic
implementations or three CHAIN schedulers.

For future target reporting, record actual standard, organization, profile,
clock ratio, queue/issue settings, native tick and elapsed ns. DDR4 uses 833 ps,
GDDR7 571 ps, HBM3 312.5 ps per tick; these raw counts are not interchangeable.
Preserve the frozen DDR4 runner's NoRefresh configuration and result/CSV
shape. HBM3's Accepted Open/AllBank evaluation and zero RFM must not be replaced
by DDR4 NoRefresh. GDDR7 requires ordinary REF and zero RFM under its Accepted
evaluation boundary. Accepted G7 selects Open + AllBank REF + zero RFM
independently on each of the four x8 Channel controllers in one GDDR7 x32
device. PerBank was considered but not selected for this runner. The existing [AllBank manager](../../../src/ramulator/controller/refresh/impl/all_bank.cpp)
already registers GDDR7_PuD at Channel scope and HBM3_PuD at PC scope.
Thus GDDR7 issues one covering refresh per controller period; HBM3 targets each
of its two PCs per controller, preserving Accepted scope across Sid/Bank sets.
Retain default scatter_interval=0 and common startup: managers are independent
but refresh demand may align across Channels. No device-wide barrier or new
staggering policy is implied. Primitive timing, queue safety and zero-RFM
validation remain unchanged.

The current total-command==PuD-occurrence assertion assumes no ordinary
maintenance/preparation. Keep maintenance-command counts, total issued-command
counts and completed PuD occurrence counts separate; Request type alone also includes preparatory PRE
for a PuD Request. Preserve occurrence-count validation and verify zero RFM,
without deleting REF or calling refresh overhead a PuD primitive occurrence.
The exact future attribution/check implementation needs review, not a change
to primitive semantics. No target timing baseline is measured here.

Runner/system consumers now include constructing 4/16 homogeneous controllers,
installing the shared global association before frontend setup, exporting both
local geometry and global bounds, collecting every per-Channel command file
(`.ch0` through `.chN-1`) and handling the controller-statistics list rather
than one controller map. Aggregate counts by summation, but measure workload
elapsed time by the global completion boundary, **not** summed controller
cycles. Preserve per-Channel observations, global Channel labels, stable merge
ordering if producing an aggregate trace, and one global CHAIN/checkpoint
namespace. Report evaluation unit, Channel/PC counts, per-Channel and aggregate
capacity/queues, frontend admission rate, residual work and maintenance counts.
These are additional consumers beyond the previous codec-only investigation.

## 8. Frozen evidence and compatibility obligations

Authoritative local frozen DDR4 evidence is `build/pud-no-engine/`, manifest
SHA-256 `f8ec33ac76cf89a13f7c6753aa5b885f752762bc6bf24b9bbea45df8de2443e1`.
Its source/provenance, results, command streams, chain CSVs, layouts and
requirements remain intact. The [plan's correction evidence](../plans/pud-multistandard-substrate-plan.md#correction-completion--2026-09-16)
already records all 14 cycle values and their unchanged relationship to Phase 1;
the numeric baseline is not duplicated here.

Exact preservation requires:

- DDR4 profile default/export values, one-rank enumeration and slot order;
  F/K/D, input/workspace/constants/temporary allocation, group/lane order,
  arithmetic/movement stream order and all Request counts.
- Legacy three-line header, CHAIN selection order/IDs, all physical line bytes,
  layout v4 fields/key order/formatting, requirements JSON/header contents.
  There are 56 generated artifacts across 14 cases.
- Initial-MUL/final indices, one-attempt-per-tick DDR4 frontend injection, retry order,
  callback after full recovery, clock ratios and chain CSV column/value order.
- Runner configuration including NoRefresh and queue/scheduler settings,
  exact command order/clocks/coordinates/types/source, 14 controller-cycle
  values, per-operation/total Request counts and command counts.
- Primitive binding timing, footprints, no-SALP, recovery/maintenance and
  completed GDDR7/HBM3 command/completion evidence. A common-code move must
  preserve these; it cannot redefine expected baselines.

Paths and infrastructure wall times are not modeled behavior, but must not be
used to normalize away differing trace/layout/count/timing data. Existing
Phase-1 historical evidence is also immutable. This investigation hashes
preserved runtime evidence; it does not remeasure cycles or regenerate it.

Inspected tests include the complete
[GEMV composition](../../../tools/pud_gemv_generator/test_integration.py) and
[frontend integration](../../../tests/unit_tests/test_pud_gemv_frontend.py)
suites, target
[GDDR7 placement](../../../tests/unit_tests/test_gddr7_pud_location.py) /
[HBM3 placement](../../../tests/unit_tests/test_hbm3_pud_location.py),
[DDR4 compute ranges](../../../tests/device_timings/test_pud_compute_ranges.py),
[GDDR7 controller](../../../tests/controller_scheduling/test_gddr7_pud.py) /
[HBM3 controller](../../../tests/controller_scheduling/test_hbm3_pud.py),
and target compute/movement Device tests. Coverage includes exact boundaries,
different Bank/PC/Sid identity, invalid topology, all ordered footprint pairs,
no-SALP, more than eight disjoint Requests and completion/retry behavior.
The completed primitive suites/evidence stay the regression authority;
passing a geometry probe does not newly validate physical DRAM behavior.

## 9. Common-code organization and implementation boundary

The common dispatcher and default `PuDBinding::command/local_timing/
conventional_closed/conventional_drained` still reside in
[pud_binding_ddr4.cpp](../../../src/ramulator/dram/pud_binding_ddr4.cpp).
Moving them to a common implementation unit would materially help if Phase 4
centralizes profile selection/export: target registration would no longer
depend on a DDR4 implementation file. It is not required to change execution
to enable the new codec; defer a move that has no touched consumer.

Likewise, three profile factories, target organization checks, table validation
and mixed-radix forward/inverse mapping remain together in
[pud_location_ddr4.cpp](../../../src/ramulator/dram/pud_location_ddr4.cpp).
When exposing a validated selected association, separating common validation/
mapping from target factory/organization data would prevent another Python
or frontend target-geometry table. Existing
[pud_location.cpp](../../../src/ramulator/dram/pud_location.cpp) is a natural
home for genuinely common resolver definitions. Keep DDR4 formulas/tables and
all target numeric bindings exact; no mapper redesign or filename-only cleanup.
This is a conditional organization recommendation, not an implementation plan
for a broad refactor. Global association construction now gives common resolver
validation/mapping a concrete first consumer; preserve target factories and
local timing/resource bindings rather than distributing device arithmetic
across controllers. The routing extension needs shared-boundary regression
coverage; a filename change alone supplies none of it.

The user's selections close G5/G7; the [canonical decision](../decisions/pud-multistandard-substrate.md)
records acceptance. The alternative codecs, resolver facade, shorter domain
policy and Bank-first enumeration above remain evidence of evaluated trade-offs.
They are not live modeling gates. The selected frontend budget differs from
current source behavior and the previous global-one-attempt proposal; the
selected HBM order replaces the prior Bank-before-BankGroup proposal.

The first implementation consumers remain system association initialization,
frontend admission/codec, layout/replay, static placement and runner reporting,
in the [Phase-4 plan](../plans/pud-multistandard-substrate-plan.md#phase-4--reusable-operationgemv-integration-and-characterization).
Implementation requires separate user approval. No new G0/G1/G2/G3/G4/G6,
finite-engine, SALP or arithmetic-precision question is opened. Physical-fidelity
limitations and deferred realistic GPU PA mapping remain as recorded in the
existing references; acceptance is not new physical calibration evidence.

## 10. Read-only validation

Executed from this checkout using
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. LD_LIBRARY_PATH=.` and
`ramulator2-venv/bin/python3`:

- In-memory `generate()` comparison for all 14 frozen DDR4 cases: layout
  serialization and physical trace plus original header/CHAIN serialization
  are byte-identical. No writer or simulator capture was invoked.
- Derived all six operation requirements and lowered each with an explicit
  512-row layout; confirmed the footprints/counts in section 4.
- Existing resolver harness probes confirmed capacity, mat/group/H and actual
  hierarchy support; capacity arithmetic used actual ancestry, not the
  DDR4-shaped test-only chip_capacity_bits field.
- Existing focused tests: 45 passed, 106 deselected, with
  `pytest -q -p no:cacheprovider tests/unit_tests/test_gddr7_pud_location.py tests/unit_tests/test_hbm3_pud_location.py tools/pud_gemv_generator/test_integration.py -k 'location or static_placement_boundaries or profile_edges_and_early_capacity_rejection or reject_unsupported_tails'`.
- Verified every file in six preserved SHA-256 manifests: Phase 1 before 124,
  Phase 1 after 122, no-engine 108, Phase 2 final 138, Phase 3 final 197, and Phase 3
  prior-baseline-regression-final 138 entries (827 manifest entries total).
  No evidence directory was written.
Continuation checks additionally passed:

- DDR4 K=1/2/16 enumeration across all eight paths, high-chip INT8 replay for
  both schedules, compute/LC range coverage and successor boundaries.
- Production GenericDRAM construction with four GDDR7 and sixteen HBM34
  controllers without installed PuD profiles; expected setup rejection with
  profiles. These construction probes did not run empty frontends or claim
  multi-Channel PuD execution. Existing CacheLineInterleave probes verified
  global routing/compaction on every Channel; local resolvers rejected both
  multi-Channel MappingContext and explicit Channel1 as expected.
- Disk-free ordinary LoadStoreTrace probes through the production memory system
  routed 32 GDDR7 / 128 HBM3 Reads across 4 / 16 controllers: eight accepted
  Reads per global Channel ID. All controllers ticked together; no PuD profile
  was installed. This proves current ordinary routing/admission, not drained
  completion, PuD device execution or new GEMV performance.
- Independent arithmetic checks confirmed aggregate capacities and all 1,024
  unique HBM global Bank coordinates in the previously investigated
  Channel/PC-first, Bank-before-BankGroup order. That historical probe does not
  validate an implementation of the subsequently selected placement order.
- Per-Channel resolver capacities, all 14 in-memory trace/layout comparisons
  and all six manifests (827 entries, manifest digests unchanged) rechecked.
- 427 focused existing tests passed, 122 deselected: DDR4/GDDR7/HBM3 location,
  paired Request/routing tests, GDDR7 four-controller configuration and GEMV
  placement/tail cases. Command: the prior pytest invocation plus
  `tests/unit_tests/test_pud_location.py`,
  `tests/unit_tests/test_pud_request_locations.py`,
  `tests/controller_scheduling/test_gddr7.py`, with selection
  `location or full_device_is_composed or static_placement_boundaries or profile_edges_and_early_capacity_rejection or reject_unsupported_tails`.
- Local documentation link/anchor checks and `git diff --check` passed at
  documentation closure. No new-target GEMV generation/execution, baseline
  regeneration, production edit or commit belongs to this investigation.

At G5/G7 acceptance documentation closure, the 14 frozen DDR4 trace/layout
byte comparisons and all six evidence manifests (827 entries, including
unchanged manifest digests) passed again. All 86 local documentation links/
anchors and `git diff --check` passed. The earlier source probes and focused
test results above remain investigation evidence; derivations were not rerun,
and no implementation or baseline regeneration was performed.
