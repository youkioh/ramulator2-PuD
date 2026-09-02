Status: Accepted

Question

What queue admission, mixed-traffic scheduling, completion, callback, latency,
and statistics semantics should apply to PuD requests?

Decision

Use a configurable dedicated pending-PuD buffer with a default capacity of 32
entries. One PuD request consumes one buffer entry regardless of its operand
count. A failed admission leaves the request retryable with its request-owned
operand vector intact. Entry-count capacity deliberately does not model the
host-memory cost of variable-length operand-vector metadata.

Preserve the existing active-buffer and FIFO priority-buffer behavior. Active
requests retain their existing precedence, and a priority request that blocks
new work continues to do so. When no priority request blocks new work, obtain
the pending-PuD candidate and the Read/Write candidate through their respective
existing scheduling paths and select the oldest timing-ready candidate between
them. Equal-arrival tie-breaking may follow a deterministic implementation
order and has no additional modeling significance. This oldest-ready
PuD-versus-Read/Write arbitration is an explicit simulator scheduling policy.
It supersedes the Phase 6 scaffolding that gave every pending PuD request
strict precedence over new Read/Write work.

Issuing a PuD request's final `PREpb` ends its command sequence, releases its
bank ownership, and removes it from schedulable controller state. Do not extend
ownership through precharge recovery. Retain the request through a minimally
generalized version of the existing pending-completion infrastructure until
the final `PREpb` issue cycle plus the accepted `nRP`. Set `depart` to that
recovery-completion cycle and invoke the request callback exactly once at that
point. Do not add a PuD-specific recovery queue. If heterogeneous completion
latencies invalidate the existing FIFO-by-depart assumption, make the shared
completion path safely identify ready completions without introducing a new
request-scheduling policy.

The callback boundary after final `PREpb` plus `nRP` is a DDR4_PuD simulator
request-lifecycle definition. It is not a claim about the earliest physical
availability of the computed data. Measure end-to-end PuD request latency as
`depart - arrive`; this includes admission and queueing delay and may therefore
exceed the isolated primitive timing.

For each of RowCopy, MAJ3, MAJ5, and NOT, record controller-level accepted
request count, completed request count, total end-to-end latency, and average
end-to-end latency. Record pending-PuD queue occupancy and average occupancy,
and include pending PuD entries in total controller queue occupancy. At the
memory-system level, record the corresponding accepted-operation counts.

Do not include PuD requests in existing Read/Write byte-throughput, row-hit,
forwarding, or write-coalescing statistics. Do not assign new PuD semantics to
`size_bytes`.

Phase 7 ingress ends at the existing Request-level
`IMemorySystem::send(Request&)` path. Do not add a new public multi-operand
`IFrontEnd` API in this phase.

Rationale

A dedicated buffer gives PuD admission explicit backpressure without coupling
PuD requests to Read/Write mode or maintenance capacity. Counting requests
rather than operands preserves support for arbitrary nonempty RowCopy
destination lists and matches the entry-count convention of existing
controller buffers.

Oldest-ready arbitration removes the temporary strict pending-PuD priority
without adding quotas or a destination-level preemption mechanism. It remains
work-conserving while allowing request age to decide between independently
ready PuD and Read/Write work.

Final `PREpb` is the accepted end of bank-scoped PuD ownership, while the
accepted primitive timing includes its `nRP` recovery. Separating sequence
retirement from external completion preserves both decisions. Reusing the
existing delayed-completion concept avoids new PuD device state or a separate
recovery queue.

PuD operations have no accepted byte-transfer or row-buffer-hit semantics.
Operation counts and end-to-end latency therefore provide lifecycle statistics
without changing the meaning of existing Read/Write statistics.

Evidence

Ramulator2 `ReqBuffer` capacity is counted in request entries, and `Request`
owns its ordered operand vector. The controller already has a
pending-completion path that retains Read requests until `depart` and then invokes
their callbacks, although its current drain and latency accounting are
Read-specific and assume compatible departure ordering.

The accepted Gate 8 timing model assigns `nRP = 16 CK` to final precharge
recovery and includes it in the simulated primitive totals. The accepted Gate
9 policy ends bank ownership when final `PREpb` issues. The accepted Gate 10
policy preserves active-buffer precedence and FIFO priority-head blocking.

Current Read forwarding, Write coalescing, row-hit accounting, byte-throughput
accounting, and memory-system accepted-request counts are explicitly
Read/Write-oriented. The existing Request-level memory-system send path already
preserves and routes PuD operand vectors.

Open issues

- Oldest-ready arbitration is a project scheduling policy, not source-backed
  physical PuD behavior.
- Entry-count admission does not bound or model operand-vector metadata
  storage.
- The callback boundary is a simulator lifecycle definition; the available
  reference does not establish the earliest physical data-availability point.
- A public multi-operand frontend API remains outside Phase 7.
