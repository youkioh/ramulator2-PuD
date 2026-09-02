# DDR4_PuD user guide

DDR4_PuD is a separate DRAM standard built from the DDR4 baseline. Standard
DDR4 has no PuD requests, commands, states, or timings. DDR4_PuD supports four
request-level operations:

| Request identifier | Primitive | Ordered operands | Lower-level sequence |
| --- | --- | --- | --- |
| `RowCopy` | Row copy | source, one or more destinations | `ACT_PUD_S_OC(src) -> ACT_PUD(dst0) -> ... -> PREpb` |
| `MAJ3` | TRA (3-input majority) | three rows | `ACT_PUD_OC(X) -> ACT_PUD(Y) -> ACT_PUD_S(Z) -> PREpb` |
| `MAJ5` | 5RA (5-input majority) | five rows | `ACT_PUD_OC(V) -> ACT_PUD(W) -> ACT_PUD(X) -> ACT_PUD(Y) -> ACT_PUD_S(Z) -> PREpb` |
| `NOT` | NOT | one source row | `ACT_PUD_S_OC(X) -> N -> PREpb` |

TRA and 5RA realize 3-input and 5-input majority, respectively. The public
request identifiers remain the consistent pair `MAJ3` and `MAJ5`. `5RA`
cannot be a C++ identifier because it begins with a digit; `MAJ3` is the
paired naming choice rather than a C++ language requirement.

The request owns the primitive identity and ordered address-vector operands.
The controller validates placement, traverses operands, retains sequence
progress, and owns the target bank from the first PuD activation through final
`PREpb` issue. The DRAM device enforces the lower-level phase states, command
legality, and timing. A sequence arrow specifies role order, not uninterrupted
channel use: timing-legal commands to non-owned banks may issue between PuD
commands.

## Reproducible isolated run

[`examples/ddr4_pud_microbenchmark_config.py`](../../examples/ddr4_pud_microbenchmark_config.py)
is an exportable configuration for the C++ microbenchmark. It selects:

- `DDR4_PuD`, `DDR4_8Gb_x8`, one rank, and the supported `DDR4_2400R` timing preset;
- `GenericDDR` with a configurable `pud_buffer_size`;
- `FRFCFS`, `Open`, `NoRefresh`, and `PassThroughAddrMapper`;
- `GenericDRAM` with `PassThroughChannelMapper`; and
- the existing text `CmdTraceRecorder`.

`NoRefresh` is intentional only for this isolated-latency run. Use an
appropriate refresh manager such as `AllBank` in traffic experiments, subject
to the refresh limitations below. The pass-through mappers are required here
because PuD operands are already final device-visible address vectors.

From the repository root:

```bash
cmake -S . -B build
cmake --build build --target ddr4_pud_microbenchmark -j
PYTHONPATH=python python3 -m ramulator export \
  examples/ddr4_pud_microbenchmark_config.py \
  -o build/ddr4_pud_microbenchmark.yaml
LD_LIBRARY_PATH=. ./build/ddr4_pud_microbenchmark \
  build/ddr4_pud_microbenchmark.yaml \
  build/ddr4_pud_trace.csv.ch0
```

The example submits one request at a time to an initially closed bank, has no
unrelated traffic or refresh, retries after backpressure, and uses source IDs
100 through 103. It prints callback/trace-derived latency components, the
controller and memory-system statistics, and checks the four isolated modeled
latencies. The command trace is written to
`build/ddr4_pud_trace.csv.ch0`; its columns are `clock`, `command`, the device
hierarchy coordinates, `type`, and `source`.

## C++ request submission

Phase 9's supported submission surface is the request-level C++ memory-system
interface, not the test-only Python controller harness:

```cpp
using Ramulator::AddrVec_t;
using Ramulator::Request;

std::vector<AddrVec_t> operands = {
    {0, 0, 0, 0, 100, 0},  // source
    {0, 0, 0, 0, 101, 0},  // destination 0
    {0, 0, 0, 0, 102, 0},  // destination 1
};
Request request(std::move(operands), Request::Type::RowCopy);
request.source_id = 100;
request.size_bytes = memory_system->get_tx_bytes();
request.callback = [](Request& completed) {
  // completed.arrive and completed.depart are controller cycles.
};

while (!memory_system->send(request)) {
  memory_system->tick();
}
```

`size_bytes` must be positive and no larger than the DRAM transaction size,
but it has no new PuD operation semantics. A `false` return is retryable
backpressure: tick and resubmit the same request. Failed admission does not
consume or reorder its request-owned operands. Do not reconstruct or move the
request between retries.

RowCopy requires a source followed by at least one destination. It has no
arbitrary primitive-specific destination limit. `MAJ3`, `MAJ5`, and `NOT`
require exactly three, five, and one operands, respectively. Submitted order
is the deterministic traversal and role-assignment convention; it is not a
claim that permutations of equivalent destinations or intermediate majority
operands change physical correctness.

## Address and placement requirements

Each operand is a full final device-visible vector in this order:

```text
[Channel, Rank, BankGroup, Bank, Row, Column]
```

Every coordinate must be within its configured hierarchy bound. For the
example's single-channel `DDR4_8Gb_x8` organization, the bounds are one
channel, one rank, four bank groups, four banks per bank group, 65,536 rows,
and 1,024 columns. All operands in one request must share channel, rank, bank
group, bank, and the derived logical subarray:

```text
subarray_id = row / 1024
local_row   = row % 1024
```

The contiguous 1,024-row logical-subarray mapping is a simulator assumption,
not a verified physical DDR4 mapping. Columns are preserved in the request
and trace but have no PuD operation semantics.

## Completion and latency

The controller releases bank ownership when the final `PREpb` issues. It
retains the unschedulable request until that issue cycle plus `nRP`, then sets
`depart` and invokes its callback exactly once. `arrive` is the successful
controller-admission cycle; `depart` is this recovery-completion cycle. This
completion boundary is a simulator lifecycle definition, not a claim about
earliest physical data availability.

Use the first command cycle for a request's unique `source_id` in the existing
command trace together with its callback timestamps:

```text
isolated modeled primitive latency = depart - first PuD command issue
pre-start delay                    = first PuD command issue - arrive
end-to-end request latency         = depart - arrive
```

Pre-start delay includes queueing, arbitration, and prerequisite work before
the primitive starts. Aggregate end-to-end latency can therefore exceed the
isolated modeled primitive latency. With `DDR4_2400R`, including final
`PREpb` recovery:

```text
RowCopy with D destinations = 40 + 5*D + 16 CK
TRA (MAJ3 request)          = 66 CK
5RA (MAJ5 request)          = 76 CK
NOT                         = 99 CK
```

## Statistics

For each operation name `rowcopy`, `maj3`, `maj5`, and `not`, the controller
exports:

- `num_pud_<operation>_reqs`: successfully accepted requests;
- `num_pud_<operation>_reqs_completed`: requests reaching completion;
- `pud_<operation>_latency`: total `depart - arrive`; and
- `avg_pud_<operation>_latency`: average `depart - arrive`.

`pud_queue_len` is accumulated pending-PuD queue occupancy over measured
cycles, and `pud_queue_len_avg` is its average. Pending PuD entries are also
included in `queue_len` and `queue_len_avg`. At memory-system scope,
`total_num_pud_rowcopy_requests`, `total_num_pud_maj3_requests`,
`total_num_pud_maj5_requests`, and `total_num_pud_not_requests` count accepted
operations.

PuD requests have no accepted byte-transfer or row-buffer-hit semantics, so
they are excluded from Read/Write throughput, forwarding, write coalescing,
and row-buffer hit/miss/conflict statistics.

## Current limitations

- The simulator does not track DRAM data values or validate functional copy,
  majority, or inversion results.
- There is no energy model, inter-column movement, or higher-level PuD operations.
- Logical-subarray placement is a simulator assumption; physical mat identity
  and interleaving remain undefined.
- There is no PuD preemption, abort, resume, refresh-postponement bound,
  retention guarantee, or variable-operand metadata-cost model.
- The accepted atomicity, reservation, command encoding, shared-resource,
  activation-window, cross-bank, refresh, and behavior-changing-plugin
  assumptions do not have physical validation. See the accepted
  [PuD decisions](decisions/) for their precise scope.
- Future real-workload or external-simulator integration must provide a
  multi-operand PuD ingress path to the existing Request-level
  `IMemorySystem::send(Request&)` interface.
