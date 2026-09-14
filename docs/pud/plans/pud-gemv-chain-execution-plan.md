# PuD GEMV Chain Execution Plan

Status: Complete. One phase, four work units and the final fresh-context audit
passed. No commit made.

## Authority and focused audit

Recover the [canonical CUDA specification](../references/gpu-pud-gemv-programming-model.cu),
[programming-model reference](../references/gpu-pud-gemv-programming-model.md),
[Accepted macro contract](../decisions/pud-gemv-macro-contract.md),
[execution/completion authority](../decisions/mimdram-movement-execution-ownership-and-device.md),
and [unified substrate](../decisions/ddr4-pud-unified-substrate.md).
The [completed integration plan](pud-gemv-trace-integration-plan.md) is prior
implementation evidence, including the original serialized frontend.

The generator already emits contiguous per-output physical sequences and
disjoint output row bands, including private micro-operation temporary rows.
Its existing flattened completion indices identify physical requests for
external domain readout; they must not become concurrent completion tallies.
No arithmetic, placement, workspace, reduction, or movement change is needed.

Before this change, `PuDTrace` retained a canonical Request across failed sends
and waited globally for its callback. `GenericDRAM::send` counts only accepted requests;
`GenericDDR::try_send_special_request` leaves failed admission retryable.
`ControllerBase::serve_completed_requests` releases recovery protection before
the callback. Existing `ReadWriteTrace` and `LoadStoreTrace` attempt one send
per frontend tick. The audit found no existing chain mechanism to reuse.

The user's requested baseline resolves the dependency and injection scope:
`PUD_TRACE` uses `CHAIN <nonnegative integer>` selection directives; requests
append to the selected chain, including when an ID recurs. IDs are opaque to
the frontend. A selection is mandatory before any physical Request; there is
no implicit chain or alternate trace-header form.
A FIFO ready-chain queue rotates after rejection and appends a chain after
completion; at most one send attempt occurs per frontend tick. Full callbacks
alone release successors. Controller/substrate arbitration stays authoritative.
No unresolved modeling gate was found. No DAG or serialized comparison mode.

## Phase invariant and work units

Each output's unchanged physical sequence is completion-ordered in one chain,
while independent chains may have requests outstanding concurrently.

| Unit | Work and focused verification | Status |
| --- | --- | --- |
| WU1 | Emit chain directives around existing output sequences; preserve flattened physical indices and all request counts. Compare one-chain and per-output executions of the same current physical stream for all three profiles. | Passed |
| WU2 | Replace global state with chain heads and a fair ready queue, one attempt/tick; add peak accepted inflight count. Build affected C++ targets. | Passed |
| WU3 | Deterministic frontend tests for callback ordering, overlap, fairness, failed-send retry and exact counts; real substrate tests for one-chain serialization and all three profiles. No arithmetic replay. | Passed |
| WU4 | Update the reference and user guide; record representative old/new cycles and peak inflight. Fresh-context audit of authority, source/schema and complete diff; affected checks, local documentation links and `git diff --check`. | Passed |

## Timing boundary

Controller cycles measure concurrent execution of the generated PuD physical
Request stream. They exclude GPU launch/duplication, transposition, readout,
conversion, and GPU residual/domain final combination, including the external
readout before workspace reuse. They are not full end-to-end GEMV latency.
Static placement capacity and existing controller resource restrictions remain.

## Verification evidence

The permanent [frontend tests](../../../tests/unit_tests/test_pud_gemv_frontend.py)
derive both executions from the same current M=2 N=12 physical Request stream
for all three profiles: one chain for the serialized reference, one chain per
output for concurrent execution. They check identical Request contents/counts,
serialization, overlap, callbacks and accounting, without historical hashes,
fixed cycle expectations or a required cycle improvement. The measurements
below were captured during implementation and are evidence, not test oracles.
Both `_ramulator` and `_ramulator_test` built successfully with required codegen;
no generated source or wrapper diff resulted.

Representative configuration: INT8 M=2 N=12, DDR4_8Gb_x8 / DDR4_2400R, one
channel/rank, installed MIMDRAM placement profile, default eight compute engines,
FRFCFS, NoRefresh, Open row policy, and frontend/memory clock ratios both one.

| Execution | Controller cycles | Peak inflight Requests | Completed Requests | Command occurrences |
| --- | ---: | ---: | ---: | ---: |
| Pre-change globally serialized frontend | 106828 | 1 (by construction) | 1456 | 5808 |
| Chain-aware frontend | 105373 | 2 | 1456 | 5808 |

The unchanged placement puts these outputs on intersecting mat resources.
Here concurrency removes submission gaps while resource conflicts still
serialize physical compute; inflight is not an active-engine metric. A separate
two-chain/disjoint-mat test checks actual overlapping command execution.
Run `PYTHONPATH=python:. python -m pytest tests/unit_tests/test_pud_gemv_frontend.py -q -s`
to measure the current comparison and run focused frontend regressions.

Initial milestone checks: 33 frontend tests passed; 14 existing Request-copy/location and
real-memory retry regressions passed. The INT8 M=1 N=12 comparison retains
exactly 53414 cycles, 728 Requests and 2904 occurrences, with peak inflight one.
The disjoint-mat test observes both chains starting before either terminal PRE.
No arithmetic or GEMV functional replay was repeated.

The independent fresh-context audit recovered the canonical `.cu`, Accepted
contracts, source/schema, tests, and complete diff; it found no correctness or
scope issues. All 31 local documentation links/anchors and `git diff --check`
passed. The final cleanup also removes the tracked local review artifact
`git_diff.log`; it is not source or documentation authority. No replacement
diff log is created. Cleanup validation passed: affected build/codegen, all 32
focused frontend tests, 44 local documentation links/anchors, and
`git diff --check` / `git diff HEAD --check`. The complete `git diff HEAD`
was reviewed with no commit blockers. The MIMDRAM placement-profile identifier
and accepted chain execution remain unchanged. No commit made.

Large-chain simulation throughput is not established: an optional M=24 N=4
concurrent timing sample was stopped after more than six minutes of simulator
wall time. No modeled-cycle or scalability conclusion uses that unfinished run.
