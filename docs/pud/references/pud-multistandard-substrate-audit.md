# PuD multistandard substrate audit

Status note: G0 was subsequently Accepted and Phase 1 completed on 2026-09-16.
The [Accepted decision](../decisions/pud-multistandard-substrate.md) and
[implementation plan](../plans/pud-multistandard-substrate-plan.md) are the
current authority. The original audit snapshot is preserved below.

Audit date: 2026-09-16. Source baseline:
`093af06009f0d3e403fc9e949682ce6722a8ec3a`
(`merge: integrate PuD operation generation and GEMV evaluation`).

This is repository evidence and an architecture investigation, not acceptance
of new geometry, timing, or execution semantics. The companion
[Proposed decision](../decisions/pud-multistandard-substrate.md) and
[conditional implementation plan](../plans/pud-multistandard-substrate-plan.md)
separate recommendations from current authority.

## 1. Checkout and evidence boundary

- Branch: `feature/pud-multistandard-substrate`; HEAD exactly matches the
  required integrated baseline. `git status --short` was empty before work.
- Read the current root [AGENTS.md](../../../AGENTS.md); it is unchanged.
  The three new documents were explicitly requested for this milestone.
- Repository root and Git common directory are this checkout and its `.git`.
  `build/CMakeCache.txt` records this checkout as `CMAKE_HOME_DIRECTORY`, this
  checkout's `build` as its cache/build directory, local `ext` dependencies,
  and `ramulator2-venv/bin/python3` in this checkout. Resolved build, environment,
  and Python package directory paths remain here.
- Inspected build/test entry points contain no dependency on the old
  experimental checkout. Historical `/tmp/pud-footprint-*` results mentioned
  in the completed footprint plan were not used. No other checkout or build
  tree was read, modified, imported, or required for this audit.
- Read-only Python serialization of the three local standard definitions
  confirmed hierarchy sizes, command ticks, transaction widths, effective
  timing values, and the timing-table gaps below. No simulator rebuild or
  regression run was performed; this is not a new baseline performance run.

Evidence labels used below:

- **Repository fact:** current source behavior, including approximations.
- **Reference fact:** evidence recorded in the supplied technical references;
  not an independent vendor validation performed in this audit.
- **Accepted project choice:** current decision authority, not a physical fact.
- **Proposal / gate:** not yet accepted or implemented.

Read authority: [unified substrate](../decisions/ddr4-pud-unified-substrate.md),
[placement](../decisions/mimdram-addressing-geometry-and-payload.md),
[execution](../decisions/mimdram-movement-execution-ownership-and-device.md),
[timing/resources](../decisions/mimdram-movement-timing-and-resource-model.md),
[target transport](../decisions/mimdram-mat-target-transport-abstraction.md),
[reduction lowering](../decisions/mimdram-reduction-placement-and-movement-lowering.md),
[operation lowering](../decisions/pud-operation-physical-lowering.md), and
[GEMV contract](../decisions/pud-gemv-macro-contract.md), plus the
[user guide](../ddr4-pud-user-guide.md).
The current-status paragraphs in canonical decisions resolve historical
acceptance-time open statements. No old target-queue implementation is needed.
The short geometry reference's “mat-level mapping is not yet defined,” the
guide's old macro-exclusion wording, and README's HBM3 hierarchy omitting Sid
are historical/stale descriptions; current decisions and source take priority.
These unrelated documents were not edited.

## 2. Actual memory-standard models

Primary code: Python [DDR4](../../../python/ramulator/dram/ddr4.py),
[GDDR7](../../../python/ramulator/dram/gddr7.py), and
[HBM3](../../../python/ramulator/dram/hbm3.py); corresponding generated
[DDR4.cpp](../../../src/ramulator/dram/impl/DDR4.cpp),
[GDDR7.cpp](../../../src/ramulator/dram/impl/GDDR7.cpp), and
[HBM3.cpp](../../../src/ramulator/dram/impl/HBM3.cpp).
The generated files register enums/handlers; Python exports numeric timing
tables. They are not separate handwritten implementations of the timings.

| Property | DDR4 | GDDR7 | HBM3 |
| --- | --- | --- | --- |
| External hierarchy, in order | Channel, Rank, BankGroup, Bank, Row, Column | Channel, Bank, Row, Column | Channel, PseudoChannel, Sid, BankGroup, Bank, Row, Column |
| Controller | GenericDDR, one command/tick | GDDR7, derived from HBMControllerBase; column then row issue slot/tick | HBM34, derived from HBMControllerBase; column on rising edges, row slot each half-cycle with pairing restrictions |
| Channel organization | One channel/Device/controller; ranks explicitly replicated | One x8 channel/Device; no Rank, BankGroup, package, or PC level | One channel/Device with two PCs; Sid is an actual modeled level, not Rank |
| Bank organization | x4/x8: 4 groups × 4 banks/rank; x16: 2 × 4 | 16 banks/channel | 4 groups × 4 banks/Sid/PC; Sid count 1, 2, or 4 |
| Prefetch / channel width / transaction | 8 / 64 bits / 64 B | 32 / 8 bits / 32 B | 8 / 32 bits / 32 B; separate PC data timing |
| Organization columns → mapped burst columns | 1024 → 128 | 2048 → 64 | 256 → 32 |
| Command timing unit | CK; baseline 833 ps | CK4; preset 571 ps/tick | Python CK=625 ps; two simulator ticks/CK; exported tick duration 312 ps |
| Command buses | One Channel bus; one CK/command | Channel row and column buses; ACT, RD/WR/AP and RCK commands occupy two CK4; PRE/REF/RFM one | Channel row and column buses shared by PCs; ACT 1.5 CK=3 ticks, PRE/REF/RFM 0.5 CK=1 tick, RD/WR/AP 1 CK=2 ticks |
| Data occupancy | nBL=4 CK, Channel; Rank/BG CAS and turnarounds | nBL=2 CK4, Channel; same-bank spacing/turnarounds | nBL=2 CK=4 ticks, PseudoChannel; Sid/BG CAS constraints |
| Subarrays/chips/mats in standard node tree | None | None | None; Sid must not be equated with the PuD Chip field |

All have one ordinary `ACT` semantic command, whole modeled bank-row state,
and ordinary `RD`, `WR`, `RDA`, `WRA`. ACT records the addressed Row in the
bank's row-state map; the tree stops before Row. Column is an external
prefetch-compacted burst selector after mapping, not an internal PuD group.
None establishes physical row-to-subarray or column-to-mat wiring.

### Organizations and presets

DDR4 has twelve organization presets: 2/4/8/16 Gb × x4/x8/x16, default one
rank, 64-bit channel. Row counts (x4, x8, x16 respectively) are:
2 Gb `(2^15,2^14,2^14)`, 4 Gb `(2^16,2^15,2^15)`,
8 Gb `(2^17,2^16,2^16)`, 16 Gb `(2^18,2^17,2^17)`.
The preset families are 1600 J/K/L, 1866 L/M/N, 2133 N/P/R,
2400 P/R/U/T, 2666 T/U/V/W, 2933 V/W/Y/AA, and 3200 W/AA/AC.
Secondary nRRDS/nRRDL/nFAW depend on DQ/rate; nRFC on density/tCK;
nREFI uses 7.8 microseconds. The PuD definitions expose only DDR4_2400R.

GDDR7 has `GDDR7_16Gb_x8`, `GDDR7_32Gb_x8`, `GDDR7_64Gb_x8`:
rows `2^14`, `2^15`, `2^16`, density fields 4096/8192/16384 Mb,
respectively. The modeled single-channel capacities are 0.5/1/2 GiB.
The names therefore do not describe the capacity of one instantiated channel.
There is no modeled package grouping that automatically creates four channels.
`GDDR7_28000_PAM3` is its only timing preset. Its comment explicitly says
CI/smoke/regression only, not a vendor timing table; the module calls
unavailable values “guesstimates.” Resolved rate is 28021, from rounded
`32*10^6/(2*571)`, rather than literal 28000.

HBM3 presets below all have DQ/channel width 32, two PCs, four groups and
four banks/group, and 256 organization columns:

| Preset | density field (Mb) | Sids/PC | Rows/bank | Capacity from modeled dimensions/channel |
| --- | ---: | ---: | ---: | ---: |
| HBM3_4Gb | 4096 | 1 | 16384 | 0.5 GiB |
| HBM3_8Gb_8hi | 8192 | 2 | 8192 | 0.5 GiB |
| HBM3_16Gb_8hi | 16384 | 2 | 16384 | 1 GiB |
| HBM3_32Gb_8hi | 32768 | 2 | 32768 | 2 GiB |
| HBM3_32Gb_16hi | 32768 | 4 | 32768 | 4 GiB |

Capacity here is a derivation from hierarchy counts × columns × configured
width, not a claim about stack/die capacity. Python's density field is used
for timing derivation, is not serialized as a C++ organization dimension,
and must not substitute for these counts. No stack-wide chip participation or
internal mat placement can be recovered from `_8hi`/`_16hi` names alone.
The sole timing preset is `HBM3_6400Mbps`. Its comments cite JESD238 for
organization and refresh derivation; the audit does not validate a complete
JEDEC implementation from those comments.

For DDR4, `channel_width / dq` gives a parallel width factor (16/8/4 for
x4/x8/x16). The standard has no Chip level or explicit participating-chip
state. The selected PuD profile interprets the x8 factor as eight chips.
GDDR7 and HBM3 have width factor one; that is not evidence for a complete
physical package/chip/mat mapping.

### Timing and command details

Baseline values before serialization scaling:

| Timing | DDR4_2400R (CK) | GDDR7_28000_PAM3 (CK4) | HBM3_6400Mbps (CK) |
| --- | ---: | ---: | ---: |
| tCK_ps | 833 | 571 | 625 |
| nRCD or nRCDRD/nRCDWR | 16 | 30 / 19 | 31 / 15 |
| nRP / nRAS / nRC | 16 / 39 / 55 | 30 / 60 / 90 | 26 / 45 / 72 |
| nWR / read-to-PRE | 18 / nRTP=9 | 30 / nRTPSB=4 | 33 / nRTP=9 |
| Read/write latency fields | nCL=16, nCWL=12 | nRL=24, nWL=6, nDQERL=0 | nCL=20, nCWL=10 |
| Activation spacing | Rank nRRDS=4, nFAW=26; BG nRRDL=6 | Channel nRRD=4; no nFAW declaration | PC nRRDS=4, nFAW=24; BG nRRDL=5 |
| Refresh example | nRFC=433, nREFI=9364 | nRFCab=315, nRFCpb=105, nREFI=3327, nREFIpb=207 | For HBM3_8Gb_8hi: nRFC=416, nRFCpb=320, nREFI=6240, nREFIpb=195 |

DDR4 commands: `ACT PREpb PREab RD WR RDA WRA REFab`.
GDDR7 adds `REFpb RFMab RFMpb RCKSTRT RCKSTOP`.
HBM3 adds `REFpb RFMab RFMpb`, without RCK commands.
The GDDR7 controller has `always_on`, `start_with_read`, and
`start_with_rckstrt` RCK modes; automatic start/stop consumes column slots.
RFM timings default to refresh timings as explicit GDDR7 placeholders; there
is no GDDR7 RFM policy. HBM3 also defaults RFM durations to refresh durations.

[DRAMStandard.to_config](../../../python/ramulator/dram/spec.py) scales
HBM3 non-rate timing fields into ticks and floor-divides tCK_ps by two.
It translates finish-reception timing to issue timestamps by:

```text
issue_gap = nominal_ticks + preceding_command_ticks - following_command_ticks
```

Bus occupancy is generated separately at Channel level, within each declared
bus. PuD phase duration must not accidentally acquire this adjustment twice,
or confuse physical phase start with completion of command reception.
HBM34's ACT-specific falling-edge pairing uses `clk+3`; other row commands
use `clk+1`. New ACT-like identities will not inherit that behavior merely by
being listed as row commands. Columns issue on odd controller ticks (rising
edges); falling edges permit only PREpb/PREab, subject to PC/bank pairing.

### Precharge, refresh, and completeness limits

[PREpb](../../../src/ramulator/dram/commands/PREpb.h) targets one full bank
on the ordinary path. [PREab](../../../src/ramulator/dram/commands/PREab.h)
uses `BankTarget::All`; actual scope is the address pattern matched against
the bank ancestry, not a fixed Rank constant. REFab/RFMab use that same target
mechanism; REFpb/RFMpb target one bank and request PREpb if necessary.

[AllBank refresh](../../../src/ramulator/controller/refresh/impl/all_bank.cpp)
constructs Rank-scoped requests for DDR4, Channel-scoped requests for GDDR7,
and PseudoChannel-scoped requests across Sids for HBM3. Its standard-name
table needs binding integration if new registrations are introduced.
[PerBank](../../../src/ramulator/controller/refresh/impl/per_bank.cpp)
round-robins flat banks. [HBM34PerBankRefresh](../../../src/ramulator/controller/refresh/impl/hbm34_per_bank_refresh.cpp)
tracks sets per PC/Sid, enqueues matching bank positions across PCs, and
retries priority backpressure; its set cooldown is recorded on enqueue,
not on actual REFpb issue. Preserve that distinction when assessing fidelity.
No deadline/retention guarantee follows from these policies.

Concrete limits requiring visibility before a new binding:

- GDDR7 has no explicit `ACT/RD/WR -> PREab` timing or `PREab -> ACT`
  recovery edge. Generated row-bus occupancy is not a replacement for these
  intervals. Existing single-bank edges do not become all-bank edges merely
  because PREab changes bank state. This is a source-table gap, not a proposed
  timing value or a fix made by this audit.
- HBM3's nominal half-cycle is 312.5 ps, but runtime `tCK_ps` is 312.
  Timing decisions expressed in ticks and time reporting therefore need an
  explicit precision policy. Do not silently change shared clock serialization
  in a PuD refactor. Its preset also explicitly supplies nRREFD=8 and nREFI=6240;
  `setdefault` means these win over the fallback formulas.
- Neither model supplies PuD commands, physical mat geometry, HFF structure,
  mat-selective PRE wiring, PRADA calibration, movement command encoding, or
  movement shared-resource evidence. Existing standard tests prove modeled
  timing relationships, not those missing physical mechanisms.

### Mapper assumptions

[AddrMapperBase](../../../src/ramulator/controller/addr_mapper/addr_mapper_base.cpp)
removes Channel, sizes fields with log2, subtracts prefetch bits from the last
Column field, and removes transaction-offset bits. Despite its DDR-style
name, [RoBaRaCoCh](../../../src/ramulator/controller/addr_mapper/impl/ro_ba_ra_co_ch.cpp)
loops over the actual hierarchy. It takes compact Column first, then levels
between Channel and Row in their declared order: Rank/BG/Bank for DDR4,
Bank for GDDR7, PC/Sid/BG/Bank for HBM3. It does not fabricate Rank.
[CacheLineInterleave](../../../src/ramulator/memory_system/channel_mapper/impl/cache_line_interleave.cpp)
uses transaction width, so its default stripe is 64 B for DDR4 and 32 B for
these GDDR7/HBM3 models. Multi-channel counts must be powers of two.
Pass-through mappers accept explicit vectors; they do not establish a
physical-bit placement map. The canonical PuD resolver currently supports
only one channel, CacheLineInterleave + RoBaRaCoCh, without remapping/offsets.

## 3. Current PuD source inventory and classification

A = reusable unchanged; B = small boundary/representation generalization;
C = DDR4 binding; D = MIMDRAM-DDR4-profile choice;
E = unresolved modeling decision. Split classifications distinguish an
algorithm from its current binding; “generic semantics” does not mean all
current structs compile unchanged for HBM3.

Source keys:

- R: [request.h](../../../src/ramulator/base/request.h),
  [request.cpp](../../../src/ramulator/base/request.cpp),
  [routing](../../../src/ramulator/memory_system/pud_request_routing.h).
- L: [pud_location.h](../../../src/ramulator/dram/pud_location.h),
  [pud_location.cpp](../../../src/ramulator/dram/pud_location.cpp),
  [validation](../../../src/ramulator/controller/pud_request_validation.cpp).
- S: [pud_sequence.cpp](../../../src/ramulator/controller/pud_sequence.cpp).
- Ctl: [ControllerBase](../../../src/ramulator/controller/controller_base.cpp),
  [GenericDDR](../../../src/ramulator/controller/impl/generic_ddr_controller.cpp).
- Dev: [Device](../../../src/ramulator/dram/device.cpp),
  [context](../../../src/ramulator/dram/device.h),
  [node timing](../../../src/ramulator/dram/node.cpp).
- Def: [ddr4_pud.py](../../../python/ramulator/dram/ddr4_pud.py),
  [ddr4_pud_movement.py](../../../python/ramulator/dram/ddr4_pud_movement.py),
  generated [compute](../../../src/ramulator/dram/impl/DDR4_PuD.cpp) and
  [combined](../../../src/ramulator/dram/impl/DDR4_PuD_Movement.cpp) definitions.

| Abstraction | Class | Concrete boundary |
| --- | --- | --- |
| Seven Request types, arity, destructive effects | A | R; keep numeric IDs and callback contract. No new standard-specific Request types. |
| PuDOccurrence, role, operand association | A/B | S; descriptor/cursor protocol reusable, command lookup bound to semantic names. |
| Primitive ordering | A | S; five PRADA sequences, including variable-destination RowCopy, remain common. |
| LC/GB occurrence ordering | A/E | S; accepted logical six/five occurrences reusable; physical command encoding on new standards requires approval. |
| Request history and copies/retries | A | R/S; Request remains sole mutable cursor/history, immutable shared locations survive copies. |
| Completion callbacks/dependencies | A | Ctl/PuDTrace; release before accounting/callback, erase ready completion before reentrant submission, no dependency inferred from submission order. |
| PlacementProfile | B/D/E | L; table-driven dimensions/permutations reusable; rank_counts, bank_groups and current transfer coverage are specialized. New physical values unknown. |
| LocationResolver | B/C/D | L; common authority, inverse/permutation/bounds logic reusable; hard-coded standard allowlist, six coordinates, one-channel DDR4 decode must be isolated. |
| ExternalRow, CellID, LayoutRegion, LocationAssociation | B | L; fixed Rank/BG fields and ranks cannot identify HBM3 PC/Sid or rankless GDDR7 without redesign of the hierarchy portion. |
| RequestLocations | B | R; retained resolver and footprint union reusable; same_bank explicitly compares Channel/Rank/BG/Bank. |
| MatRange and FULL_MAT | A | L; inclusive nonempty range, construction-only FULL_MAT immediately resolves. |
| Chip/mat mapping | D/E | L; uniform chip-major segmentation, eight chips and sixteen mats/chip are current profile properties, not new-standard facts. |
| Subarray/local-row derivation | B/D/E | L/geometry; integer division/remainder helper reusable only for an approved contiguous-row profile; 1024-row grouping is a project assumption. |
| HFF/group mapping | A/D/E | L; typed Group versus BurstColumn and ordered permutations reusable; H=4, 128 groups, identity tables and G=B are this profile. |
| Physical mat footprint | A/B | R; normalized union of resolver-produced chip/mat segments ignores operand row/column; bank identity needs generalization. |
| GB successor topology | A/D/E | L; relation lookup reusable; same-chip forward local neighbor without wrap is this profile's accepted topology. No automatic new edges. |
| PuDExecutionContext | A | Dev; one invocation phase and location association, no copied cursor or payload. |
| ProtectedPuD records | A/B | Ctl; ownership/lifetime common; engine pool domain supplied by approved binding. |
| Engine allocation | A/B/D/E | GenericDDR oldest-first first-fit algorithm reusable; extract it from tick integration. E=8 per controller/channel is the present profile choice, not an HBM PC fact. |
| Movement acquisition | A | Ctl; atomic first ACT acquisition, no engine, no ownership during preparatory ordinary PRE. |
| Conflict checking | A/B | R/Ctl/Dev; all six pair classes use footprint intersection; ordinary/maintenance use complete target-bank scopes. Change identity, not policy. |
| No-SALP rule | A | Same-bank different-subarray invocations serialize through recovery; separate CellIDs do not grant SALP. |
| Recovery lifetime | A/B/C | Ctl; hold engine/footprint through completion; literal terminal issue+nRP is the current DDR4 anchor needing a binding interval/anchor for multi-cycle standards. |
| PRADA A/A_S/A*/A_S*/N effects | A | S/Dev; activation, sensing, aggregate inversion semantics are independent of external hierarchy. |
| Numeric PRADA-derived timing | C/E | Def; 11/5/40/34/43 CK constants belong to calibrated DDR4_2400R, not a generic default. |
| CK conversion | B/E | spec.py; conversion machinery exists, but tick precision and command-reception anchoring require care for new bindings. |
| PRE / nRP use | A/C/E | Shared PREpb semantic ID is available on all three standards; range-local effect is common policy, physical applicability and recovery anchor are not established for new standards. |
| Invocation-local timing helper | B | S; current helper scans nonsibling Bank edges against this Request's history. Six movement dependencies directly read nRCD/nRTP, names absent or different on targets. |
| Shared command timing | C/B/E | Dev has two scalar CA deadlines; PuD updates only root Channel history. Adequate for current single-bus binding, insufficient for arbitrary PC/Sid/BG shared constraints or dual-bus selection. |
| Conventional DRAM interaction | B/C | Preserve full ordinary tree timing. New bindings must explicitly cover PRE/AP/REF/RFM recovery into PuD and PuD's applicable outgoing shared edges. |
| ACT_MOV/RD_MOV/WR_MOV | A/B/E | Generic simulator identities, non-opening/non-accessing/non-closing metadata, Single bank target; bus class/occupancy not yet bound for GDDR7/HBM3. |
| LC timing graph | A/C/E | Occurrence graph reusable as hypothesis; nRCD/nRTP/nRAS/nRP/nWR/nRELOC choices are DDR4-calibrated policy. |
| GB timing graph | A/C/E | Particular source ACT versus latest destination ACT must remain distinct; 1 ns relocation is a project assumption, not universal hardware timing. |
| Movement PRE semantics | A/E | Source LC PRE retains valid data metadata; terminal PRE closes own invocation; no disjoint state reset. New physical realization remains unproven. |
| Movement resource scope | A/E | Accepted common physical-footprint policy, including disjoint GB progress; any extra new-standard shared physical constraint requires evidence/approval. |
| Operation generator | A | Symbolic PRADA arithmetic in tools/pud_operation_generator; no standard timing/hierarchy dependency. |
| Physical lowering | A | PhysicalRowLayout supplies local_row_count and designated rows; allocation does not choose bank/mats. Default helper's 1024 is a convenience, not target geometry. |
| Operation requirements | A/B | Counts derived from fixed lowered ADD/MUL programs; target layout must separately check row capacity. Do not duplicate arithmetic requirements per standard. |
| GEMV generation | B/D/E | Reads C++ profile, but factory is fixed; placement emits [0,0,bg,bank], one rank, uniform chip ranges. BLP enumeration of PCs/Sids and group-order compatibility are gates. |
| PuDTrace | A/B | Dependency queue, retry fairness, callbacks and opaque checkpoints reusable; PROFILE/RANKS header and four-coordinate context parser are DDR4-shaped. |
| GEMV baselines/execution | A/B/E | Keep both arithmetic schedules and completion boundaries; profile dimensions, placement enumeration and time units require target validation. |
| Experiment runner | B/C | Reuse generation/report/count logic; DDR4_PuD_Movement/GenericDDR/configuration and four-field placement labels are hard-coded. |

The term `DDR4_PuD_Movement` does not imply movement-only semantics; it is the
public combined registration. The PRADA phase definitions within `DDR4_PuD`
and LC/GB occurrence semantics within its extension are generic mechanisms
despite their containing class names. `GenericDDR` similarly contains
reusable allocation/admission logic mixed with single-bus tick arbitration.
`is_inherited_pud_request_type` and `legacy_pud_statistic_*` denote the five
current compute types, not an alternate public legacy path.

Generated Cmd templates are already shared. Canonical associated PuD dispatch
bypasses their old bank-aggregate actions and uses invocation phases; tests
of raw command handlers alone cannot verify canonical range behavior.
Validation still contains legacy fallback constants 128 mats/16 mats per chip;
public canonical ingress rejects unlocated requests. Do not make that fallback
the new-standard implementation.

## 4. Where the three mechanisms meet

The actual path is resolver/profile → paired Request → GenericDRAM routing →
GenericDDR allocation/arbitration → PuDOccurrence + invocation context →
Device local/shared timing → terminal recovery → callback. GenericDRAM's
`location_resolver()` currently returns the first controller's resolver, and
its admission checks that association. Multi-controller PuD therefore needs
explicit routing/association work if selected; ordinary multichannel support
does not establish it automatically.

The C++ factory exposed by
[bindings.cpp](../../../src/ramulator/python/bindings.cpp) supplies the sole
current geometry to [GEMV generation](../../../tools/pud_gemv_generator/generator.py).
This avoids a second geometry table, but the no-argument factory always
selects DDR4. Group transfer lowering uses `offset / H`; although validation
uses `group_position_to_column`, arbitrary nonidentity group layouts are not
automatically supported by the generator.
[PuDTrace](../../../src/ramulator/frontend/impl/memory_trace/pud_trace.cpp)
uses the installed resolver, but parses DDR4 context coordinates.
[The runner](../../../experiments/pud_gemv_baseline.py) builds the canonical
one-rank DDR4 configuration and reports controller ticks as cycles.

### PRADA evidence and numeric derivation

[Primitives](pud-primitives.md) and the
[timing reference](ddr4-pud-timing-reference.md), especially §11, distinguish
mechanisms from portable numbers. PRADA supplies tOC=5 ns, tN=35 ns and
temporal NOT=81.32 ns for its studied technology. The project assumes
tCS=4 ns, consistent with the waveform and the derived RowCopy difference
131.64−81.32=50.32 ns. DDR4_2400R contributes tRP=16×0.833=13.328 ns.
Thus T_ACT_P=81.32−35=46.32 ns and
tSR=46.32−5−4−13.328=23.992 ns. tSR is calibrated, not directly measured.

| Phase | Physical-model interval | Independently rounded DDR4 CK |
| --- | --- | ---: |
| A* | tOC+tCS = 9 ns | 11 |
| A | tCS = 4 ns | 5 |
| A_S* | tOC+tCS+tSR = 32.992 ns | 40 |
| A_S | tCS+tSR = 27.992 ns | 34 |
| N | tN = 35 ns | 43 |
| P recovery | ordinary selected nRP | 16 |

These constants are stored in Python presets, not dynamically recalibrated
when tCK/nRP overrides are supplied. The <0.5% MIMDRAM ACT overhead check
applies a 1.005 envelope to continuous ACT phases; it does not change these
four rounded DDR4 intervals. That result must be recomputed at another tick
resolution, not generalized as “zero overhead.”

New-standard alternatives are materially different: retain assumed physical
phase times and change PRE; retain aggregate NOT calibration and recompute
tSR using new PRE; or use target-specific circuit evidence to recalibrate
phases. The first two are hypothetical portability policies, not source facts.
Pure unit conversion is possible only after selecting physical times and
phase/command anchors. None is chosen here. PRADA's activation-current
argument is not automatic evidence for a GDDR7/HBM3 hybrid or for movement.

### MIMDRAM profile and movement evidence

[Geometry](mimdram-geometry.md), [movement](mimdram-inter-column-data-movement.md),
and [mapping/reduction](mimdram-data-mapping-and-vector-reduction.md) report
the evaluated eight chips, sixteen mats/chip, 1K rows/mat, 512 columns/mat,
four HFFs/mat and seven-bit chip/mat encoding. Repeating those dimensions in
each derived subarray, chip-major physical-bit striping, ordered cells 4G+h,
contiguous row subdivision, and numeric forward-neighbor topology are
accepted project placement choices. They are not vendor wiring facts.

LC retains source HFF validity across source PRE; GB uses activated endpoints
and the neighboring global movement path. Published aggregate equations are
LC `2*(tRAS+tRP)+tRELOC+tWR` and GB `tRAS+tRELOC+tWR+tRP`.
The project's use of FIGARO's guarded 1 ns for both paths and the following
directed decomposition are assumptions, not timing tables for new standards:

| Graph | Occurrence-specific edges | Additional invocation-history edges |
| --- | --- | --- |
| LC: ACT0,RD1,PRE2,ACT3,WR4,PRE5 | 0→1 nRCD; 1→2 nRTP; 4→5 nRELOC+nWR | ACT_MOV→PRE/WR nRAS; PRE→ACT_MOV nRP |
| GB: ACT0,ACT1,RD2,WR3,PRE4 | 0→2 nRAS; 2→3 nRELOC; 3→4 nWR | ACT_MOV→PRE/WR nRAS; terminal recovery nRP |

DDR4 issue clocks are LC `[0,16,39,55,94,114]`, completion 130;
GB `[0,1,39,41,59]`, completion 75. Range width changes LC payload, not
occurrence count or isolated latency. GB's source dependency must not be
replaced by the latest destination ACT timestamp.
There are no modeled target queues, functional HFF values, movement DQ
turnarounds, movement nRRD/nFAW constraints, or extra shared GB link owner.
Omitted costs/exclusions are fidelity choices, not proof of physical freedom.

## 5. Minimum architecture derived from the audit (Q1–Q6)

**Q1 — one substrate:** yes for semantics, sequencing, invocation state,
ownership, first-fit allocation, no-SALP conflicts, and recovery/completion
policy. No source evidence requires three copies. Placement identity and
issue integration need generalization; PuDTrace's scheduler can remain one
implementation while its physical context codec becomes hierarchy-aware.

**Q2 — binding inputs:** the minimum is resolved command capability/IDs and
metadata; close command and completion interval/anchor; numeric local edges
and occurrence delays; shared edge scopes/publication; command bus class,
occupancy and edge legality; incoming conventional recovery including refresh;
profile/resolver selection, bank-context identity and engine-pool association.
Use DRAMSpec's existing names, sizes, metadata and command templates wherever
possible. Keep primitive sequence construction common; there is no evidence
for a general user-programmable sequence API. A thin generated standard
registration is acceptable; duplicated execution implementations are not.

**Q3 — timing:** retain physical-time provenance separately from cycle values.
Do not map DDR4's nRCD to a target read/write split by spelling alone, or reuse
11/5/40/34/43, nRELOC=2, or one-CK issue occupancy. New calibration,
movement delay selection, half-cycle precision and reception anchors are gates.

**Q4 — profile:** existing organization supplies hierarchy, row/column counts,
DQ, width, prefetch, transaction size and external mapping order. It does not
supply mats/chip, rows/mat, HFFs, participating physical components, bit
striping, physical row subdivision or GB adjacency. MIMDRAM supplies a
mechanism and one DDR4 evaluation, not missing GDDR7/HBM3 values.
Require a separately named, provenance-labeled coordinated profile for each
approved target. No name/value set is selected here.

For the current exhaustive all-mats burst model, check:

```text
organization_columns * dq = mats_per_chip * cells_per_mat_row
dq * prefetch = mats_per_chip * hffs_per_mat
organization_columns / prefetch = cells_per_mat_row / hffs_per_mat
chips * dq = participating payload width
```

These equations constrain a proposed profile but do not uniquely establish
physical geometry. Keeping DDR4's 16×512 and H=4 fails GDDR7's row/burst
coverage and HBM3's burst coverage. A different participation/grouping model
needs an explicit replacement contract. Also require row subdivision,
bit-map inverse/bijection, group order, mat namespace/contiguity, topology,
capacity and mapper/remap validation. Unsupported profiles must fail closed.

**Q5 — hierarchy:** identify a bank by the actual prefix through Bank, within
the resolver/routing association; retain Subarray/LocalRow and physical mat
segments separately. This is a proposed representation, not a physical
resource decision. Do not add dummy Rank/BG or alias PC/Sid to Rank/Chip.
HBM PC/Sid placement, engine sharing and any cross-PC execution remain gates.
Existing target-bank enumeration can preserve maintenance scopes. Shared
timing publication must address real hierarchy levels without publishing
range-local PRE/phase deadlines into ordinary bank histories.

**Q6 — movement:** preserve logical endpoint order, HFF-position correspondence,
source-valid lifetime and common footprint policy. Bind physical geometry and
topology, command encoding/bus use, local interval graph values, and any
evidence-backed shared constraints separately. New topology is excluded;
if an approved target cannot realize the existing directed one-hop model,
stop rather than invent connectivity. All-bank commands are never substitutes
for invocation-local terminal close.

## 6. Decision Gates and required information

Each target resolves its own G1–G4/G6 entries. A DDR4-preserving refactor does
not require inventing their answers. G0 requires review of the concrete proposal.

| Gate | Required decision/evidence; alternatives and trade-off | First consumer |
| --- | --- | --- |
| G0 Common architecture | Approve the companion proposal: common execution plus small bindings and real hierarchy identity. Keeping fixed DDR4 structs would instead force adapters with lost/fictional coordinates. | Phase 1 extraction/representation changes |
| G1 Physical profile | Provide target organization plus source-supported mat/HFF/row geometry, participation, bit placement and directed adjacency; alternatively explicitly authorize hypothetical modeled profiles, with labeled fidelity limits. Multiple dimension/striping solutions exist. | Target PlacementProfile factory/resolver, before any executable binding |
| G2 Compute calibration and clock anchors | Supply target phase evidence, or approve a hypothetical physical-time policy versus aggregate recalibration; decide quantization and command-reception/phase/recovery anchors, including HBM half-cycle precision. These policies yield different latency and current assumptions. | Target timing definitions, local edge conversion and completion binding |
| G3 Hierarchy and shared resources | Decide GDDR7 modeled channel/package interpretation, HBM PC/Sid placement and engine-pool domain; approve PuD row/column bus classes, command durations/edge legality and applicable shared current/resource rules. Per-controller versus per-PC engines changes capacity, not just names. | Target controller integration and shared Device timing publication; resolve with G2/G4 |
| G4 Movement portability | Establish/approve target LC/GB interval decomposition, nRCDRD/nRCDWR/nRTP-or-nRTPSB use, relocation time, mat-selective close and omitted/shared datapath constraints. Retain common footprint concurrency unless physical evidence justifies a new decision. | Target movement timing/command binding; resolve with G1–G3 |
| G5 Physical trace compatibility | Approve a hierarchy-aware context encoding for new profiles while preserving existing DDR4 trace bytes/reader behavior. A versioned named hierarchy header avoids fictional rank fields; separate per-standard frontends would duplicate semantics. Exact grammar remains to review. | First generalized PuDTrace parser/emitter, before target trace generation |
| G6 Baseline model adequacy | Resolve GDDR7 missing PREab edges from supplied standard evidence, or explicitly bound an approximate experimental configuration; decide HBM tick reporting/precision and clarify density/organization interpretation. A correction is separate reviewed scope, not a silent PuD change. | Target standard binding/validation; shared clock changes must precede dependent timing |
| G7 GEMV placement portability | Approve target BLP enumeration across actual banks/PCs/Sids/channels, capacity fallback and group-order compatibility while retaining both schedules. Do not infer a new policy from DDR4's one-rank iteration order. | Target GEMV placement adapter and experiment configuration |

No supplied repository reference establishes GDDR7/HBM3 physical mat profiles
or PRADA calibration. Those are current stop conditions for dependent work,
not blockers to completing this audit. An API sketch is not acceptance of
physical parameters. New accepted architecture belongs in the companion
decision; profile/movement refinements should update the existing canonical
placement and timing/execution authorities rather than create one file per gate.

## 7. Verification inventory and limits

Existing tests cover the right invariants but do not replace a before/after
behavioral record:

- `tests/unit_tests/test_pud_location.py` and `test_pud_request_locations.py`:
  forward/inverse placement, bounds, nonidentity synthetic maps, retained
  association, physical footprints. Synthetic profiles are software checks,
  not physical evidence for GDDR7/HBM3.
- `tests/device_timings/test_ddr4_pud.py`, `test_ddr4_pud_movement.py`, and
  `test_pud_compute_ranges.py`: definitions, ordinary recovery, exact phase
  boundaries, range-local association/timing and shared Channel behavior.
- `tests/controller_scheduling/GenericDDRController/test_pud_*.py` and
  `test_movement_*.py`: ingress, allocation, all compute/LC/GB conflict pairs,
  no-SALP, promotion pressure, maintenance, protected recovery, reentrancy,
  counts, moved bits and command visibility.
- `tools/pud_operation_generator/tests`: arithmetic, physical lowering and
  requirements; `tools/pud_gemv_generator/test_integration.py`: both baseline
  graphs, placement, counts and capacity; `tests/unit_tests/test_pud_gemv_frontend.py`:
  actual execution, retries/chains, terminal recovery and experiment reporting.
- GDDR7/HBM3 have Device timing, controller scheduling, smoke and
  latency/throughput cases; HBM34 has explicit edge/pairing and refresh-set
  tests. These conventional suites are affected by shared controller/Device
  work even before either standard supports PuD.

Phase 1 must compare full DDR4 issue streams with clocks/addresses, isolated
latencies, resolver outputs, overlap/recovery events, Request counts,
requirements/layout/trace artifacts and representative GEMV cycles. Existing
GEMV tests often assert counts and relative/positive timing rather than a fixed
baseline cycle oracle. Capture a fresh baseline from this checkout before
editing code; do not reuse historical pre-footprint GEMV cycles or artifacts.
