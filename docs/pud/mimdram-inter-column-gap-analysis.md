# MIMDRAM Inter-Column Movement — Ramulator2 Gap Analysis

Status: Working analysis

- `docs/pud/references/mimdram-inter-column-data-movement.md` is the authority
  for reference-backed physical facts.
- This document is a snapshot of the current Ramulator2-PuD architecture and
  its representation gaps.
- Alternatives and recommendations in this document are not accepted project
  decisions.
- Accepted choices will be recorded separately under `docs/pud/decisions/`.
- This analysis may later be marked superseded once the implementation plan is
  established.

---


The current architecture can support a stable, bank-conservative LC-MOV/GB-MOV model without adding `Mat` as a DRAM hierarchy level or modeling HFF/global-SA data explicitly. A larger architectural extension is required only if the model must expose per-mat concurrency, true dual-address device commands, simultaneous command issue, cross-bank/controller movement, or ISA-level `bbop_mov` lowering.

Before a plan can be stable, six plan-shaping decisions need agreement. The curated reference does not resolve them.

Legend: **P** = decide before planning; **G** = later Decision Gate; **R** = existing abstraction is reusable.

## Architecture-gap map

| Area | 1. Source-of-truth requirement | 2. Current Ramulator2-PuD behavior | 3. Concrete gap | 4. Viable abstractions | 5. Status |
|---|---|---|---|---|---|
| Physical hierarchy | Mats exist physically, but the reference explicitly does not require a simulator `Mat` level. The mapping among bank, subarray, chip, and logical mat remains unresolved. | DDR4_PuD has `[Channel, Rank, BankGroup, Bank, Row, Column]`; timing nodes stop before `Row`. Internal geometry only provides `rows_per_subarray`. [dram_spec.h](/workspaces/ramulator2-PuD/src/ramulator/dram/dram_spec.h:26) | No per-chip/mat namespace or node exists. This matters only if mat-local timing/state must be independently visible. | Keep mats as derived/request metadata; add substrate-internal mat resource tables; or add an explicit hierarchy level if later fidelity requires it. | **R:** no standalone need for a `Mat` hierarchy. The chosen placement/resource scope determines whether an extension is needed. |
| Logical mat placement | LC-MOV uses one logical mat range; GB-MOV uses separate source/destination ranges. IDs contain chip and mat bits. Multi-mat LC behavior, GB range pairing, namespace scope, and physical hierarchy mapping are unresolved. [reference §4](/workspaces/ramulator2-PuD/docs/pud/references/mimdram-inter-column-data-movement.md:550) | Existing PuD placement derives a logical subarray as `row / 1024` and requires all operands to share channel/rank/BG/bank/subarray. | That mapping does not define MIMDRAM logical mats, chip identity, range pairing, or reachability. It must not be promoted into a MIMDRAM mapping. | Define an initial supported subset and derive mat metadata from addresses; carry explicit logical ranges; or add a separate placement map. | **P** |
| Operation boundary and taxonomy | The reference exposes both ISA-level `bbop_mov(...size,n)` and physical LC-MOV/GB-MOV transfers. Each evaluated physical transfer moves four bits. | Global request types are the four existing PuD primitives; helper logic and statistics assume their contiguous IDs. The public surface is direct C++ `Request` submission. [request.h](/workspaces/ramulator2-PuD/src/ramulator/base/request.h:13) | There is no accepted choice between one high-level move, explicit LC/GB requests, or one request per physical transfer. `size_bytes` must currently be 1–transaction-sized, so it cannot naturally express a four-bit transfer or a large `bbop_mov`. | Add LC-MOV/GB-MOV request types; add a generic movement request lowered by the controller; or place `bbop_mov` lowering above the memory system. | **P** |
| Operand representation | Each movement needs source and destination row, column, and logical mat range. | `Request::operands` owns an ordered vector of full `AddrVec_t`; columns are preserved. | Two addresses fit, but logical mat ranges, element count, bit precision, and movement width do not. Device calls receive only one `AddrVec_t`. | Extend each movement operand with mat-range metadata; use request-side parallel metadata; or derive it from an accepted mapping. Avoid adding hierarchy coordinates solely to transport metadata. | **P** for the metadata contract; ordered operand ownership itself is **R**. |
| Placement reachability | LC is intra-mat. The shown GB path is neighboring `SA_(i-1) → SA_i` within a chip; cross-chip movement is not supported by the depicted path. Non-neighbor routing and wider-range pairing are unresolved. | Current validation accepts same logical subarray and has no chip, neighbor, direction, or range checks. | Current placement would accept combinations that are not justified for MIMDRAM and reject others without a MIMDRAM basis. | Initially restrict to single-mat LC and one supported same-chip neighboring GB pair; define repeated hops; or accept a broader abstract connectivity model explicitly as a project choice. | **P** |
| Request multi-operand handling | Movement has two semantic endpoints. | Request-owned operand vectors survive copies, buffering, retries, and callbacks. | No fundamental container gap. Existing validation and fixed request-type switches must be generalized. | Reuse the vector with source at index 0 and destination at index 1, plus accepted per-endpoint metadata. | **R** |
| Command granularity | LC has source `ACT→RD→PRE`, retained data, then destination `ACT→WR→PRE`. GB concurrently activates source and destination, then source RD, destination WR, and recovery. Mat-queue variants exist, but their exact use for movement is unresolved. | A controller-sequenced request exposes one intended command and one address at a time. GenericDDR issues at most one command per tick. [generic_ddr_controller.cpp](/workspaces/ramulator2-PuD/src/ramulator/controller/impl/generic_ddr_controller.cpp:205) | Two concurrent GB activations cannot be represented faithfully as two ordinary commands without serializing them. A single device command cannot currently receive both endpoints. | Aggregate the whole move; expose movement-specific phases with one combined dual-activation command; or extend the controller/device APIs for simultaneous multi-address issue. Mat-queue transport can be hidden, represented as metadata, or exposed. | **P** |
| Device state and prerequisites | LC physically retains HFF data across source PRE. GB temporarily has two active mat rows and source data in the HFF/global-SA path. These facts do not require explicit simulator state. | State and prerequisite handlers operate on one bank node and one address. A bank has one state plus a row-state map with no mat key. [device.h](/workspaces/ramulator2-PuD/src/ramulator/dram/device.h:35), [node.h](/workspaces/ramulator2-PuD/src/ramulator/dram/node.h:32) | Explicit phase visibility would require distinguishing source/destination mat state or “movement payload valid.” Bank state cannot express that today. | Hide persistence inside an aggregate/owned sequence; add a minimal movement phase state; or add per-mat sidecar state. Explicit HFF values are unnecessary unless functional data or interfering operations depend on them. | **G**, after command granularity and interleaving are fixed. |
| Multiple simultaneously active resources | GB physically activates two mats concurrently and uses source/destination local paths plus a neighboring global-SA link. | `BankTarget` supports one bank, all banks, or same-numbered banks. Timing and actions use one address path. | No command can atomically identify two mat endpoints or reserve a link. Per-mat overlap cannot be checked. | Treat the operation as one bank-scoped aggregate; represent source, destination, and link as controller/device-side resource keys; or extend commands and timing to multi-target operations. | **P** for required concurrency fidelity and timing/resource scope. |
| Controller sequence progress | Ordered physical phases must not be lost or duplicated. High-level moves may require repeated physical transfers or hops. | `pud_sequence_index`, request-owned operands, retained active requests, and prerequisite-safe advancement already implement monotonic compound progress. [generic_ddr_controller.cpp](/workspaces/ramulator2-PuD/src/ramulator/controller/impl/generic_ddr_controller.cpp:80) | Only the current four hard-coded sequences are supported. A high-level move may need nested transfer/hop counters. | Reuse the cursor pattern; extend it to phase/transfer/hop progress only as required by the chosen operation boundary. | **R** |
| Ownership and scheduler eligibility | MIMDRAM does not specify simulator atomicity or legal interleaving. Placement, physical resource usage, and ownership are separate questions. | A retained PuD request owns one flat bank derived from operand 0. Conflicting candidates are rejected before prerequisite resolution. [scheduler contract](/workspaces/ramulator2-PuD/src/ramulator/controller/scheduler/i_scheduler.h:16) | Mat-range ownership or a request spanning multiple banks cannot be expressed. Promotion/retirement bookkeeping also assumes one bank/address. | Reuse whole-bank ownership if both endpoints are guaranteed in that bank; otherwise give requests explicit owned-resource sets and use set intersection in eligibility. | **P** |
| Timing representation | LC and GB provide aggregate equations, not a simulator timing graph. `tRELOC` is related FIGARO evidence, not direct validation of both MIMDRAM paths. | Directed timing constraints can exist at hierarchy levels, including automatically generated command-bus occupancy. [spec.py](/workspaces/ramulator2-PuD/python/ramulator/dram/spec.py:207) | No LC/GB command graph, mat/link timing scope, or accepted conversion against a target preset exists. One-address hierarchical timing cannot express two different mat endpoints directly. | Use command-edge constraints at bank/rank scope; add sidecar resource availability for mats/links; or extend timing to multi-address resources. | **G**, once command boundaries and resource scope are known. |
| RD/WR/PRE semantics | Movement RD/WR use internal HFF/global-SA paths. LC source PRE must preserve HFF data. Exact movement PRE scope is unresolved. | Ordinary RD/WR require a conventionally opened row and inherit normal column/data-bus timing. They are marked accesses and affect `ClosedCAP`. `PREpb` closes the whole modeled bank and clears all row state. [RD.h](/workspaces/ramulator2-PuD/src/ramulator/dram/commands/RD.h:10), [PREpb.h](/workspaces/ramulator2-PuD/src/ramulator/dram/commands/PREpb.h:10) | Reusing ordinary RD/WR would implicitly consume conventional bus resources and maintenance semantics not established by the source. Ordinary PRE cannot preserve a visible movement state or close one mat selectively. | Movement-specific RD/WR/PRE variants; aggregate transfer phases; or deliberate reuse of ordinary commands only with an explicitly accepted broader bank/bus abstraction. | **G** |
| Refresh, row policy, maintenance | The movement reference does not define refresh/preemption/interruption. Persistent intermediate conditions must not be corrupted if exposed. | Existing bank ownership defers intersecting PRE/REF/maintenance. FIFO priority-head blocking and current hook order are preserved. `ClosedCAP` treats ordinary RD/WR as accesses. | The existing rule works only for bank-scoped ownership. Mat-level ownership requires refresh to intersect a broader scope than ordinary traffic, and movement RD/WR classification affects row-policy behavior. | Reuse bank-level non-preemption; extend resource intersection for mat owners; decide whether priority work may bypass; classify movement phases independently of ordinary accesses. | **G** |
| Completion and statistics | Both latency equations include final recovery, but the source does not define simulator callback or statistics semantics. | PuD retirement currently hard-codes completion at final command plus `nRP`; the callback path safely handles heterogeneous departure order and reentrancy. Statistics are fixed to four operation names. [controller_base.cpp](/workspaces/ramulator2-PuD/src/ramulator/controller/controller_base.cpp:272) | An aggregate move may already include recovery; a high-level move may contain many transfers. Existing request-type detection and fixed statistics arrays do not accommodate new operations. | Reuse delayed completion and callbacks; make terminal recovery request/command-specific; add operation counts and latency, with transferred bits/elements only if their semantics are accepted. | **G** |
| Public integration and functional behavior | `bbop_mov` starts from arrays, indices, size, and precision; the control unit derives placement and LC/GB selection. | Ramulator accepts final device-visible addresses and does not model data values, arrays, allocation, or functional copying. | Exact ISA-level lowering and functional validation have no existing layer. | Keep the initial boundary at explicit physical movement requests; add a later placement-aware adapter; or build a MIMDRAM control/placement layer. | **P** if `bbop_mov` is in scope; otherwise a documented limitation. |

## Minimum decisions required before writing the plan

1. **Feature home and abstraction boundary**

   Decide whether movement extends the existing `DDR4_PuD` substrate or belongs in a separate MIMDRAM-oriented substrate, and whether the supported request is:

   - one physical LC-MOV/GB-MOV transfer;
   - an LC/GB operation spanning multiple ranges/transfers; or
   - ISA-level `bbop_mov` requiring placement-aware lowering.

2. **Placement scope and logical-mat contract**

   Define the target DRAM organization and how a request identifies a logical mat/range. The initial legality rules must explicitly cover:

   - LC same-mat placement;
   - GB same-chip requirement;
   - neighbor direction/reachability;
   - single-mat versus wider ranges;
   - source/destination range pairing;
   - column-address units and transfer width.

   The reference cannot justify arbitrary non-neighbor, cross-chip, or multi-range behavior.

3. **Command granularity**

   Decide which phases are independently visible and how GB’s concurrent activations are represented: hidden aggregate behavior, a combined dual-activation phase, or true simultaneous multi-command issue.

4. **Timing/resource scope**

   Separately decide the required concurrency fidelity:

   - conservative bank-scoped timing;
   - independent mat-local resources;
   - explicit source/destination/link resources;
   - any rank/channel command or data-path occupancy.

   This determines whether the existing timing tree is sufficient.

5. **Ownership/atomicity scope**

   Independently decide whether a movement owns the whole bank, only its mat ranges/link, multiple banks, or another resource set, and what ordinary/PuD work may interleave.

6. **Required state visibility**

   Decide whether intermediate phases are externally schedulable enough that Ramulator must preserve mat-active or payload-valid state. This does not mean HFF/global-SA values must be modeled; it determines whether any minimal sidecar/device state is required.

## Questions that can remain Decision Gates inside the plan

After the six decisions above, the plan can retain gates for:

- exact movement command names and whether MIMDRAM mat-queue variants are explicit or abstracted;
- minimum device states and prerequisite/action tables;
- ordinary versus movement-specific RD/WR/PRE mapping;
- the directed timing graph, preset-specific cycle conversion, `tRELOC` treatment, bus occupancy, and activation-current interaction;
- refresh, row-policy, priority-buffer, plugin, and existing DDR4_PuD primitive interaction;
- pending-buffer sharing, mixed-traffic arbitration, fairness, and high-level transfer quantization;
- ownership-release, recovery, callback, and completion boundaries;
- movement statistics and trace observability;
- validation limits, especially the absence of functional data-value checking.

## Limitations that could force a larger extension

A larger architecture change is conditional, not currently inevitable:

| Required fidelity | Current limitation | Likely extension |
|---|---|---|
| Per-mat overlap and timing | No mat/chip resource identity in state or timing | Per-bank sidecar resource model or explicit `Mat` hierarchy |
| Explicit two-endpoint device phase | Device APIs receive one command and one address | Multi-address command payload or resource-set API |
| Two separately issued concurrent ACTs | GenericDDR issues one command per tick | Atomic combined command, or multi-issue controller/device support |
| Movement spanning multiple banks | Ownership, active bookkeeping, and retirement assume one flat bank | Multi-resource ownership and active tracking |
| Cross-channel movement | One request is routed to one controller | Cross-controller orchestration |
| ISA-level `bbop_mov` | No array placement/control-unit model | New frontend/control/placement layer |
| Functional result checking | No DRAM data-value model | Data-state simulation or an external functional checker |

The least expansive viable architecture is therefore a direct LC-MOV/GB-MOV request interface with explicit logical-mat metadata, accepted same-controller placement, bank-scoped timing and ownership, movement-specific aggregate or phase commands, controller-held progress, and no explicit HFF/global-SA data. That is an available abstraction, not a recommendation or accepted decision.
