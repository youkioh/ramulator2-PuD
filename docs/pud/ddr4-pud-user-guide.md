# DDR4 PuD user guide

The canonical DDR4 PuD model is one unified compute-and-movement substrate.
It combines PRADA-derived RowCopy, majority, and NOT mechanisms with the
project's MIMDRAM-shaped mat placement, range-local execution, and LC-MOV /
GB-MOV support. This is a project simulator architecture: it is not a claim
that PRADA and MIMDRAM are one physical design.

The public request types are:

| Request identifier | Operation | Ordered operands | Lower-level sequence |
| --- | --- | --- | --- |
| `RowCopy` | Row copy | source, one or more destinations | `ACT_PUD_S_OC(src) -> ACT_PUD(dst0) -> ... -> PREpb` |
| `MAJ3` | three-row majority (TRA) | three distinct rows | `ACT_PUD_OC(X) -> ACT_PUD(Y) -> ACT_PUD_S(Z) -> PREpb` |
| `MAJ5` | five-row majority (5RA) | five distinct rows | `ACT_PUD_OC(V) -> ACT_PUD(W) -> ACT_PUD(X) -> ACT_PUD(Y) -> ACT_PUD_S(Z) -> PREpb` |
| `NOT` | in-place NOT | source | `ACT_PUD_S_OC(X) -> N -> PREpb` |
| `NOT_COPY` | NOT-and-copy composition | source, destination | `ACT_PUD_S_OC(src) -> N -> ACT_PUD(dst) -> PREpb` |
| `LCMOV` | LC-MOV | source endpoint, destination endpoint | `ACT_MOV -> RD_MOV -> PREpb -> ACT_MOV -> WR_MOV -> PREpb` |
| `GBMOV` | GB-MOV | source endpoint, destination endpoint | `ACT_MOV -> ACT_MOV -> RD_MOV -> WR_MOV -> PREpb` |

`MAJ3` and `MAJ5` are the public names for TRA and 5RA. `NOT_COPY` is
a request-level composition of existing commands, not a separate physical
DRAM command.

## Canonical configuration

The currently supported placement profile is
`MIMDRAM_DDR4_8Gb_x8_v1`. It requires this coordinated configuration:

- `DDR4_PuD_Movement` with `DDR4_8Gb_x8`, `DDR4_2400R`, and
  `hffs_per_mat=4`;
- one channel, with `CacheLineInterleave`;
- `GenericDDR` with `RoBaRaCoCh`, no row remapping or reserved-row offset,
  and `pud_placement_profile="MIMDRAM_DDR4_8Gb_x8_v1"`; and
- one or four ranks.

`DDR4_PuD_Movement` is the retained implementation registration that contains
all compute and movement command definitions. It does not denote a separate
movement execution model.

The controller parameter `pud_compute_engines` is the positive compute-engine
capacity E for one controller/channel instance, shared across its Banks and
Ranks. Its default is 8. E=1 is a serialized control; larger values permit
eligible requests on disjoint ranges to overlap. `pud_buffer_size` separately
bounds resident PuD requests and defaults to 32.

The canonical example configuration is
[`examples/ddr4_pud_microbenchmark_config.py`](../../examples/ddr4_pud_microbenchmark_config.py).
Its essential component tree is:

```python
dram = ramulator.dram.DDR4_PuD_Movement(
    org_preset="DDR4_8Gb_x8",
    timing_preset="DDR4_2400R",
    rank=1,
    hffs_per_mat=4,
)
controller = ramulator.controller.GenericDDR(
    dram=dram,
    pud_buffer_size=32,
    pud_placement_profile="MIMDRAM_DDR4_8Gb_x8_v1",
    pud_compute_engines=8,
    scheduler=ramulator.scheduler.FRFCFS(),
    refresh_manager=ramulator.refresh_manager.NoRefresh(),
    row_policy=ramulator.row_policy.Open(),
    addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
    controller_plugins=[
        ramulator.controller_plugin.CmdTraceRecorder(
            path="build/ddr4_pud_trace.csv",
        ),
    ],
)
memory_system = ramulator.memory_system.GenericDRAM(
    clock_ratio=1,
    controllers=[controller],
    channel_mapper=ramulator.channel_mapper.CacheLineInterleave(),
)
```

`NoRefresh` is intentional for isolated latency and overlap checks. Use an
appropriate refresh manager such as `AllBank` for traffic experiments, subject
to the refresh limitations below.

## Constructing compute requests

Obtain the installed shared resolver from the memory system. Every operand must
be resolved through it and must explicitly select either the whole modeled mat
range or an inclusive `MatRange`:

```cpp
auto resolver = memory_system->location_resolver();

std::vector<Ramulator::PuD::PairedOperand> operands;
for (int row : {100, 101}) {
  operands.push_back(resolver->pair(resolver->compute_footprint(
      Ramulator::PuD::ExternalRow{0, 0, 0, 0, row},
      Ramulator::PuD::FULL_MAT)));
}

Ramulator::Request request(
    resolver, std::move(operands), Ramulator::Request::Type::RowCopy);
request.source_id = 0;
request.size_bytes = memory_system->get_tx_bytes();
```

For a narrower computation, replace `FULL_MAT` with an explicit inclusive
range:

```cpp
resolver->compute_footprint(
    Ramulator::PuD::ExternalRow{0, 0, 0, 0, row},
    Ramulator::PuD::MatRange{15, 18})
```

`FULL_MAT` is resolved immediately to
`MatRange{0, resolver->logical_mats() - 1}`. Both forms therefore use the
same validation, allocation, timing, recovery, and completion path. Omitting
the target is invalid; bare `AddrVec_t` operands cannot establish the required
profile and resolved range.

All operands in a compute request must share Channel, Rank, BankGroup, Bank,
derived subarray, and mat range. `MAJ3` and `MAJ5` additionally require
distinct physical rows. RowCopy accepts one source followed by one or more
destinations; the other compute operations require exactly three, five, one,
and two operands for `MAJ3`, `MAJ5`, `NOT`, and `NOT_COPY`,
respectively.

## Constructing movement requests

Movement uses the same resolver and paired-operand Request constructor. Each
endpoint explicitly identifies its row, inclusive mat range, and ordered
`Group`.

An LC-MOV uses one common range for its source and destination endpoints:

```cpp
using namespace Ramulator;

PuD::MatRange mats{15, 18};
std::vector<PuD::PairedOperand> operands;
operands.push_back(resolver->pair(resolver->group_footprint(
    PuD::ExternalRow{0, 0, 0, 0, 100}, mats, PuD::Group{3})));
operands.push_back(resolver->pair(resolver->group_footprint(
    PuD::ExternalRow{0, 0, 0, 0, 101}, mats, PuD::Group{4})));

Request request(resolver, std::move(operands), Request::Type::LCMOV);
request.size_bytes = Request::kMovementSizeBytesNotApplicable;
```

A GB-MOV uses explicit singleton endpoints. The selected profile accepts only
its directed same-chip neighbor topology:

```cpp
std::vector<PuD::PairedOperand> operands;
operands.push_back(resolver->pair(resolver->group_footprint(
    PuD::ExternalRow{0, 0, 0, 0, 100},
    PuD::MatRange{6, 6}, PuD::Group{3})));
operands.push_back(resolver->pair(resolver->group_footprint(
    PuD::ExternalRow{0, 0, 0, 0, 101},
    PuD::MatRange{7, 7}, PuD::Group{4})));

Request request(resolver, std::move(operands), Request::Type::GBMOV);
request.size_bytes = Request::kMovementSizeBytesNotApplicable;
```

LC-MOV range width determines moved bits as
`selected_mat_count * hffs_per_mat`. GB-MOV moves
`hffs_per_mat` bits. The `-1` size is a named not-applicable contract, not
a byte count. Movement does not consume a compute engine, but its accepted
Bank-aggregate conflict policy serializes it against same-Bank compute,
ordinary traffic, and other movement through recovery.

## Submission, recovery, and callbacks

Attach the callback before submission and retry the same Request after ticking
when `send()` reports backpressure:

```cpp
request.callback = [](Ramulator::Request& completed) {
  // completed.arrive and completed.depart are controller cycles.
  // completed.pud_locations retains the immutable resolved operands.
};

while (!memory_system->send(request)) {
  memory_system->tick();
}
```

A successful admission owns the request once. Failed admission does not consume
or reorder its operands. Do not reconstruct or move the Request between
retries.

Compute allocation reserves one engine and the complete resolved range
atomically using oldest-to-newest first fit. Disjoint ranges in the same
subarray may progress concurrently when E permits; intersecting ranges and
different subarrays of the same Bank conflict. The reservation starts before
the first PuD activation and remains protected through terminal `PREpb` plus
`nRP` recovery. Protection is released before exact-once accounting and the
callback.

## Canonical benchmark commands

From the repository root:

```bash
cmake -S . -B build
cmake --build build --target ddr4_pud_microbenchmark mimdram_movement_microbenchmark -j $(nproc)

PYTHONPATH=python python3 -m ramulator export \
  examples/ddr4_pud_microbenchmark_config.py \
  -o build/ddr4_pud_microbenchmark.yaml
LD_LIBRARY_PATH=. ./build/ddr4_pud_microbenchmark \
  build/ddr4_pud_microbenchmark.yaml \
  build/ddr4_pud_trace.csv.ch0

PYTHONPATH=python python3 -m ramulator export \
  examples/mimdram_movement_microbenchmark_config.py \
  -o build/mimdram_movement_microbenchmark.yaml
LD_LIBRARY_PATH=. ./build/mimdram_movement_microbenchmark \
  build/mimdram_movement_microbenchmark.yaml \
  build/mimdram_movement_trace
```

The first benchmark exercises all compute requests with explicit subranges and
`FULL_MAT`, disjoint-range overlap, dependency callbacks, LC-MOV, and GB-MOV.
The second runs focused movement cases. Both use controlled unique source IDs.

To compare compute-engine capacities, set only E when exporting:

```bash
for engines in 1 2 8; do
  RAMULATOR_PUD_ENGINES=$engines PYTHONPATH=python python3 -m ramulator export \
    examples/ddr4_pud_microbenchmark_config.py \
    -o build/ddr4_pud_microbenchmark_e${engines}.yaml
  LD_LIBRARY_PATH=. ./build/ddr4_pud_microbenchmark \
    build/ddr4_pud_microbenchmark_e${engines}.yaml \
    build/ddr4_pud_trace.csv.ch0
done
```

## GEMV trace generation and execution

Authoritative semantics are in the
[programming-model reference](references/gpu-pud-gemv-programming-model.md)
and [canonical CUDA specification](references/gpu-pud-gemv-programming-model.cu).
The `.cu` is specification code, not generator runtime input.
The accepted restriction is `N > 0 && N % HFFS_PER_MAT == 0`, with
`HFFS_PER_MAT=4`. N need not be divisible by 512: N=516 is supported.
One-to-three-element tails are rejected; no masking, padding, or host tail
fallback is provided.

From the repository root, using the repository Python environment:

```bash
cmake -S . -B build
cmake --build build --target _ramulator -j $(nproc)

PYTHONPATH=python python3 -m tools.pud_operation_generator.requirements --out build/pud-gemv/generated
for baseline in MIMDRAM-InterMatFirst MIMDRAM-IntraMatFirst; do
  for format in int8 fp8-e4m3 fp8-e5m2; do
    PYTHONPATH=python python3 -m tools.pud_gemv_generator --profile "$baseline-$format" --m 2 --n 516 --out build/pud-gemv
  done
done
```

Each GEMV invocation writes `<profile>.layout.json` and `<profile>.trace`
under `build/pud-gemv/`, plus `generated/pud_operation_requirements.json`
and `generated/pud_operation_requirements.h`. The layout records placement,
resources, and expected request counts; the trace contains one
dependency chain per output with its physical requests in completion order.
Use `--m 2` or larger to generate multiple chains. Requirements can also be
generated independently as shown above.

To generate and run one baseline independently of pytest, use the
[standalone experiment runner](../../experiments/pud_gemv_baseline.py) from the
repository root in the same Python environment:

```bash
PYTHONPATH=python:. python3 experiments/pud_gemv_baseline.py --profile MIMDRAM-InterMatFirst-int8 --m 2 --n 12 --out build/pud-gemv --csv build/pud-gemv/results.csv
```

It uses the canonical one-rank configuration above and prints JSON with output
placement, compute/LC-MOV/GB-MOV and total Request counts, peak inflight and
controller cycles. Omit `--csv` to skip appending the same fields to a CSV file.

The standalone runner also measures each output chain's MUL and reduction
phases within that same full execution. It requires one domain per output
(currently N <= 8192); longer inputs interleave MUL and reduction across domains
and are rejected by this experiment. General GEMV generation and PuDTrace
execution still support multiple domains.

Add `--chain-csv` to write `<out>/<profile>.chains.csv` with `chain_id`,
`first_submit_cycle`, `mul_complete_cycle`, `final_complete_cycle`,
`start_delay_cycles`, `mul_cycles`, `reduction_cycles`, and `chain_cycles`.
Cycles start at zero. First-submit is successful admission, and both completion
timestamps come from full Request callbacks, including terminal recovery:

```text
start_delay_cycles = first_submit_cycle
mul_cycles        = mul_complete_cycle - first_submit_cycle
reduction_cycles  = final_complete_cycle - mul_complete_cycle
chain_cycles      = final_complete_cycle - first_submit_cycle
```

Waiting before the first accepted Request contributes only to start delay;
waiting after MUL completion contributes to reduction. With no physical
reduction (N=4), MUL and final completion coincide. The JSON/summary CSV adds
mean, min, max, p50, p95 and p99 for each phase and the whole chain, plus mean
start delay. Percentiles interpolate sorted samples at `(count - 1) * p`.
Use a new summary CSV when its existing header predates these fields.

Layout schema 4 adds `chain_id`, `first_request_index`, and
`initial_mul_final_request_index` per output, using one-based flattened
physical indices; the final Request is already identified by the last domain's
`completion_index`. Trace contents are unchanged. The runner converts the MUL
boundary to a one-based index within its chain and configures PuDTrace's optional
`latency_chain_ids` and `latency_checkpoint_requests` parallel lists. The frontend
reports matching `first_submit_cycles`, `checkpoint_complete_cycles`, and
`final_complete_cycles` lists with opaque `latency_chain_ids`; it assigns no
arithmetic meaning. Unreached timestamps are -1. Collection requires equal
frontend/memory clock ratios (both one here), so acceptance and callback clocks
share controller-cycle units.

The only active schedules are **MIMDRAM-InterMatFirst** (full-vector forward
GB-MOV/ADD, then the sink's LC-MOV/ADD tree) and **MIMDRAM-IntraMatFirst**
(local LC-MOV/ADD trees first, then residual-only forward GB-MOV/ADD).
Each supports `int8`, `fp8-e4m3`, and `fp8-e5m2`, yielding the six exact
`--profile` values constructed above. The generic profiles `int8-gemv`,
`fp8-e4m3-gemv`, and `fp8-e5m2-gemv` are rejected; no aliases or old
placement modes remain. FP8 profiles are validated against their own schedule
graphs; the two orders need not produce equal results.

Both use identical [Accepted BLP-first placement](decisions/pud-gemv-macro-contract.md):
all bank-group/bank pairs before another legal K-mat range slot, then chip,
subarray capacity fallback and row-band capacity fallback. M=2,N=12 uses
bank0/mat0 and bank1/mat0; M=2,N=516 uses bank0/mats0..1 and bank1/mats0..1.
Subarrays provide capacity only; no SALP is modeled or assumed. Each output
reserves its maximum domain K and each domain uses the required prefix.
No ranged operation combines different outputs. Layout schema 4 records the
explicit baseline, arithmetic format and placement policy, alongside each
domain's physical `mat_begin`. Regenerate older layouts/traces. See the
[placement contract](references/gpu-pud-gemv-programming-model.md#baseline-placement-and-physical-trace-contract).

Use the one-rank `memory_system` component tree from
[Canonical configuration](#canonical-configuration), with `import ramulator`.
Run this Python code in the same environment with `PYTHONPATH=python`:

```python
frontend = ramulator.frontend.PuDTrace(
    clock_ratio=1,
    path="build/pud-gemv/MIMDRAM-InterMatFirst-int8.trace",
)
sim = ramulator.Simulation(frontend, memory_system)
sim.run()
stats = sim.stats
sim.finalize()
print(stats["frontend"])
print(stats["memory_system"]["controller"])
```

Select another explicit baseline/format trace by changing `path`. Frontend counters
`physical_requests_submitted`, `physical_requests_completed`, and
`physical_command_occurrences_completed` show stream execution; compare the
request counts with the layout's `request_count` and `request_counts`.
`physical_requests_peak_inflight` reports peak accepted but not yet completed
Requests, including queued work and recovery. Values above one verify
outstanding-request overlap, not necessarily simultaneous DRAM command execution.
Controller counters are described under [Statistics](#statistics).
`sim.finalize()` flushes the configured command recorder; see
[Command traces and latency](#command-traces-and-latency) for its output.

PuDTrace reads `PUD_TRACE` with `CHAIN <id>` selections, as defined in the
[physical trace contract](references/gpu-pud-gemv-programming-model.md#baseline-placement-and-physical-trace-contract).
The frontend treats IDs as opaque dependency identities. It permits one
outstanding Request per chain and releases the next only on full completion.
Its fair ready queue makes at most one send attempt per frontend tick, rotating
rejected chains for retry and appending newly ready chains after callbacks.
A `CHAIN` selection is mandatory before any physical Request.

Controller cycles model concurrent execution of the generated PuD physical
Request stream, **not full end-to-end GEMV latency**. GPU launch/x duplication,
transposition, readout/conversion, and residual/domain final combination remain
excluded, including readout before workspace reuse. Static placement and the
controller/substrate's timing and resource conflicts still constrain overlap.
The [baseline plan](plans/pud-gemv-baselines-plan.md) reports compute primitive,
LC-MOV, GB-MOV and total physical Request counts, controller cycles and peak
inflight for both baselines under identical placement. Repeat with `--n 12`
for the focused K=1 case. Cycles are performance evidence, not a fixed oracle.
Historical same-bank characterization remains in its completed plan and is
not an active evaluation policy.

## Command traces and latency

`CmdTraceRecorder` writes one file per channel by appending `.ch0`,
`.ch1`, and so on to its configured path. Text traces have this schema:

```text
clock,command,Channel,Rank,BankGroup,Bank,Row,Column,type,source
```

`type` is the numeric request identifier and `source` is `source_id`.
Compute commands carry the selected operand Row; whole-mat-row compute has no
single burst selector, so its projected Column is `-1`. Mat ranges and groups
are retained in `Request::pud_locations`, not added to the trace schema.
The controlled benchmarks print those resolved endpoints and use unique source
IDs to correlate commands. A production trace alone cannot reconstruct
arbitrary concurrent request identities or ranges.

Use callback timestamps and the first/last traced commands as follows:

```text
modeled primitive latency = depart - first PuD command issue
pre-start delay           = first PuD command issue - arrive
end-to-end latency        = depart - arrive
terminal recovery         = depart - terminal PREpb issue
```

At `DDR4_2400R`, uncontended first-command-through-recovery anchors are:

| Operation | Modeled latency |
| --- | ---: |
| RowCopy with D destinations | `40 + 5*D + 16 CK` |
| MAJ3 | `66 CK` |
| MAJ5 | `76 CK` |
| NOT | `99 CK` |
| NOT_COPY | `104 CK` |
| LC-MOV | `130 CK` |
| GB-MOV | `75 CK` |

The totals already include terminal `nRP`. Queueing, engine/range allocation,
maintenance, and shared command arbitration can increase end-to-end latency.

The current T-A abstraction delivers each resolved row/range to its
`ACT_PUD*` occurrence atomically at issue. It omits physical target-delivery
latency, mat-queue stalls, and target-delivery-specific C/A contention. Those
costs are omitted, not physically zero. Ordinary shared command occupancy and
the accepted local timing constraints still apply.

## Statistics

For each compute operation name `rowcopy`, `maj3`, `maj5`, `not`, and
`not_copy`, the controller exports accepted and completed counts, total
`depart - arrive` latency, and average latency. LC-MOV and GB-MOV use
`lcmov` and `gbmov` and additionally report exact moved bits.

`pud_queue_len` accumulates resident PuD-buffer occupancy over measured
cycles, and `pud_queue_len_avg` is its average. PuD requests have no accepted
ordinary byte-transfer or row-buffer-hit semantics, so they are excluded from
Read/Write throughput, forwarding, write coalescing, and row-buffer
hit/miss/conflict statistics.

## Current limitations

- The simulator does not store DRAM values or validate functional copy,
  majority, inversion, or movement results.
- Arithmetic macros, ADD/MUL, GEMV/GEMM generation, reduction execution, a
  compiler, and a functional workload ISA are not implemented by this
  substrate.
- The supported placement is a documented simulator profile, not verified
  vendor DDR4 wiring. Other organizations and remapping contexts require
  separately supported profiles.
- GB-MOV is limited to the selected directed singleton same-chip neighbor
  topology. LC/GB movement retains conservative Bank-aggregate concurrency.
- There is no PuD preemption, abort, resume, refresh-postponement bound,
  retention guarantee, or physical target-transport resource model.
- The accepted activation-current, command encoding, shared-resource,
  conflict, and movement timing assumptions are simulator choices with the
  fidelity limits recorded in the current
  [PuD decisions](decisions/).
