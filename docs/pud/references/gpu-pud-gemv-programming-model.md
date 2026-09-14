# GPU-PuD GEMV Programming Model

## Status and provenance

The canonical **project programming-model specification** is
[`gpu-pud-gemv-programming-model.cu`](gpu-pud-gemv-programming-model.cu).
This Markdown explains and summarizes that repository source; the `.cu`
defines the interfaces and exact macro graph. Its temporary-row ownership,
arithmetic graph, and GPU completion are project contracts, not MIMDRAM or
PRADA source facts. The
[MIMDRAM mapping/reduction reference](mimdram-data-mapping-and-vector-reduction.md)
separately records those papers' mechanisms and evidence limits.

The `.cu` preserves the reviewed INT8, FP8-E4M3, and FP8-E5M2 specification.
It is specification code, not a required build target: operation interfaces
are declarations. The operation generator emits the requirements header.
Repository recovery uses this source and its summary together.

The [prototype Python GEMV macro generator](../../../tools/pud_gemv_generator/generator.py)
implements the same semantics directly, without parsing CUDA or using the `.cu`
as runtime input. It emits physical primitive and movement requests for the
existing unified substrate. The GPU interfaces remain specification declarations.
The
[integration plan](../plans/pud-gemv-trace-integration-plan.md) tracks that work.

The [Accepted macro contract](../decisions/pud-gemv-macro-contract.md) requires
N > 0 and N divisible by HFFS_PER_MAT (four). N need not be divisible by
MAT_SIZE: partial final mats such as N=516 remain supported. Arbitrary
one-to-three-element tails are rejected. There is no partial-group movement,
masking, padding, or host tail fallback.

## PuD objects and input organization

`pud_obj_init(void *ptr, size_t element_count, size_t element_size)` marks an
already allocated GPU-visible object as a PuD object. The programming model
assigns transparent conversion between normal GPU-visible layout and DRAM
bitslice layout to a memory-controller-side data transposition unit. The call
is not an allocation or a specification of numeric input values. The prototype
integration does not implement that unit or assign its latency.

For `y = A x`, `A` has shape `[M][N]`, `x` has shape `[N]`, and `y`
has shape `[M]`. The three explicit `duplicate_x_int8`,
`duplicate_x_fp8_e4m3`, and `duplicate_x_fp8_e5m2` GPU kernels construct
an independent x copy for each output:

```text
x_duplicated[i][j] = x[j]
```

The host setup marks A, duplicated x, and each of the three macro workspaces
with `pud_obj_init()`. It does not mark the original x, GPU output y, or PuD
micro-operation-level temporary rows. The example uses M=2048, N=128 and 256 GPU
threads per block; these are example workload/launch choices, not fixed GEMV
dimensions.

## Explicit micro-operation-level and macro-operation interfaces

All six `pud_vector_*` functions are **PuD micro-operation-level interfaces**.
Each takes typed `src_a`, `src_b`, and distinct `dst` pointers,
`element_count`, and an inclusive `mat_begin, mat_end` range.

| Storage type | MUL interface / generator profile | ADD interface / generator profile |
| --- | --- | --- |
| `int8_t` | `pud_vector_mul_int8` / `int8-mul` | `pud_vector_add_int8` / `int8-add` |
| `pud_fp8_e4m3_t` (raw `uint8_t`) | `pud_vector_mul_fp8_e4m3` / `fp8-e4m3-mul` | `pud_vector_add_fp8_e4m3` / `fp8-e4m3-add` |
| `pud_fp8_e5m2_t` (raw `uint8_t`) | `pud_vector_mul_fp8_e5m2` / `fp8-e5m2-mul` | `pud_vector_add_fp8_e5m2` / `fp8-e5m2-add` |

INT8 MUL computes the complete signed 16-bit internal product and exports
only its low eight bits. INT8 ADD computes the signed nine-bit internal sum
and exports only its low eight bits. There is no saturation or separate
truncation operation. Each FP8 interface uses its corresponding
[existing generator arithmetic](../../../tools/pud_operation_generator/README.md),
including its bounded numerical domain and approximation/truncation behavior;
this specification adds no rounding or special-value policy.

The separate `pud_gemv_int8`, `pud_gemv_fp8_e4m3`, and
`pud_gemv_fp8_e5m2` GPU kernels are **PuD macro-operation interfaces**,
corresponding to prototype profiles `int8-gemv`, `fp8-e4m3-gemv`, and
`fp8-e5m2-gemv`. Each takes typed A, duplicated x, and y pointers; M and N;
`tmp_row`, `reduction_tmp_row`, `movement_tmp_row`; and
`temporary_elements_per_thread`. One GPU thread computes one y[i].

E4M3 and E5M2 remain separate public operations and macros. Shared internal
implementation does not replace these with a generic FP8-plus-format API.
GEMV composes MUL followed by ADD operations; **no PuD FMA operation exists**.

## Two temporary-row ownership scopes

A temporary row belongs to one of these two scopes; workspace roles do not
introduce further temporary-row categories.

**PuD micro-operation-level temporary rows** are private physical rows required
within one lowered ADD/MUL operation. Their requirement comes exclusively
from `tools/pud_operation_generator` analysis/lowering. Its current
`additional_temporary_rows` metric excludes designated input, constant, and
output rows. These rows are compiler/OS-managed, reserved in the selected
physical mat range, and bound by the operation lowerer. They are not
GPU-visible objects, kernel pointer arguments, or `cudaMalloc` allocations
and do not use `pud_obj_init()`.

The specification includes the generated
`generated/pud_operation_requirements.h`, supplying:

```text
PUD_INT8_ADD_TMP_ROWS        PUD_INT8_MUL_TMP_ROWS
PUD_FP8_E4M3_ADD_TMP_ROWS    PUD_FP8_E4M3_MUL_TMP_ROWS
PUD_FP8_E5M2_ADD_TMP_ROWS    PUD_FP8_E5M2_MUL_TMP_ROWS
```

Same-mat PuD operations are serialized. Therefore, each macro's micro-operation-level
requirement is the maximum of its corresponding ADD and MUL requirements:

```text
PUD_GEMV_INT8_OP_TMP_ROWS =
    MAX(PUD_INT8_MUL_TMP_ROWS, PUD_INT8_ADD_TMP_ROWS)
PUD_GEMV_FP8_E4M3_OP_TMP_ROWS =
    MAX(PUD_FP8_E4M3_MUL_TMP_ROWS, PUD_FP8_E4M3_ADD_TMP_ROWS)
PUD_GEMV_FP8_E5M2_OP_TMP_ROWS =
    MAX(PUD_FP8_E5M2_MUL_TMP_ROWS, PUD_FP8_E5M2_ADD_TMP_ROWS)
```

These are requirements, not hand-maintained numeric constants or a dynamic
temporary-row allocator. Reuse must wait for preceding operation completion.

**PuD macro-operation-level temporary rows** retain values across multiple operations.
The GEMV macro owns their placement and three distinct workspace roles:

| Specification argument | Role |
| --- | --- |
| `tmp_row` | Primary product values; alternate intra-mat reduction output when needed. |
| `reduction_tmp_row` | Forward-fold accumulated results; alternate intra-mat reduction output when needed. |
| `movement_tmp_row` | LC-MOV/GB-MOV destinations consumed by subsequent ADD or preservation moves. |

The host example allocates these three GPU-visible buffers before launch and
marks each with `pud_obj_init()`. Their element capacity per output is:

```text
temporary_elements_per_thread = min(ceil(N / 512), 16) * 512
buffer element count = M * temporary_elements_per_thread
```

Each output uses its own segment in each buffer and reuses that segment across
its reduction domains. These are logical element-buffer capacities, not
micro-operation-level physical-row requirements. Concrete physical placement belongs
to the macro generator. Inputs and outputs of each ADD/MUL use distinct row
sets under the [Accepted physical-lowering contract](../decisions/pud-operation-physical-lowering.md).
Alternating the primary/reduction roles preserves that constraint.

## Movement, placement, and exact reduction graph

The specification sets 512 element positions per mat, 16 mats per chip-local
reduction domain, and four HFF positions per mat. A domain holds up to 8192
elements. These are the selected project baseline; the
[Accepted placement profile](../decisions/mimdram-addressing-geometry-and-payload.md)
supplies their modeled physical correspondence.

`pud_mov(src, src_offset, dst, dst_offset, element_count, element_size)`
expresses logical element movement. The macro lowers same-mat movement to
LC-MOV and legal forward neighboring-mat movement to GB-MOV. For bitsliced
eight-bit values, a physical four-HFF transfer moves four bits of one
bit-plane, not four complete values. Group selectors and movement legality
come from the existing location authority; the logical offsets do not
authorize arbitrary physical shifts or partial-group writes.

For each output, process domains in increasing input-index order. Within
each domain:

1. Let L be its valid element count, K=`ceil(L/512)`, and
   v=`L - (K-1)*512`. Multiply its A and duplicated-x elements into the
   primary workspace using the corresponding MUL profile.
2. Initialize the accumulator to the primary workspace. For each source mat
   from 0 through K-2, move its full 512-element accumulator into the movement
   workspace of the next mat. ADD that destination mat's primary products as
   the left operand and the moved accumulator as the right operand, writing
   the reduction workspace. Use 512 valid local products except in the last
   mat, where only v participate. Copy the moved suffix `[v,512)` unchanged
   into the reduction workspace when that last mat is partial. The reduction
   workspace becomes the next source accumulator.
3. The highest participating reachable mat, K-1, is the sink. For K=1 its
   current values are the primary workspace and its valid count is v. For
   K>1 its current values are the reduction workspace and its valid count
   is 512. The other primary/reduction workspace is the alternate.
4. Apply the intra-mat graph below using LC-MOV and the corresponding ADD.
5. Perform the GPU scalar residual/domain combine below.

Mat numbers above denote domain-local positions mapped to consecutive,
reachable mats. The [Accepted forward-fold policy](../decisions/mimdram-reduction-placement-and-movement-lowering.md)
governs low-to-high GB-MOV and the highest reachable sink. Domains remain
separate across unsupported chip/connectivity boundaries; no reverse,
wraparound, or cross-chip GB path is implied.

The three `pud_reduce_inside_mat_*` helpers use this exact graph, with offsets
relative to the sink mat and corresponding typed operations:

```text
current, alternate, movement = the three distinct workspace roles
if valid_count is not a power of two:
    target = floor_power_of_two(valid_count)
    extra = valid_count - target
    move current[target : target+extra] -> movement[0 : extra]
    ADD(current[0 : extra], movement[0 : extra]) -> alternate[0 : extra]
    copy current[extra : target] -> alternate[extra : target] if nonempty
    swap(current, alternate)
    valid_count = target

while valid_count > 4:
    half = valid_count / 2
    move current[half : valid_count] -> movement[0 : half]
    ADD(current[0 : half], movement[0 : half]) -> alternate[0 : half]
    swap(current, alternate)
    valid_count = half

return current and valid_count
```

The irregular prepass occurs before the four-residual stopping check. The
Accepted N constraint makes its moves whole-group aligned; three valid
elements are outside the supported domain. These slices specify logical
results, not implicit physical active-lane masking.

## GPU scalar completion and integration boundary

For each domain, initialize `domain_sum` to zero and ADD each returned
residual in increasing k order. Then update
`output_sum = ADD(output_sum, domain_sum)`, with output_sum initially zero
and domains processed in increasing order. Finally write y[i].

INT8 scalar `wrap_add_int8` adds the unsigned byte representations modulo
256 and returns the signed byte. E4M3 and E5M2 separately use
`pud_fp8_e4m3_scalar_add` and `pud_fp8_e5m2_scalar_add`, respectively,
with the same numerical semantics as their own operation profiles and initial
encoding `0x00`. The actual kernels use these helpers for both residual and
domain combination. No wider accumulation, reassociation, or zero-padding
identity is implied.

The macro generator owns GEMV scheduling, data/mat placement, both temporary-row
placements, operation instantiation, and reduction topology. The operation
generator remains authoritative for arithmetic primitives and micro-operation-level
requirements. The thin Ramulator frontend consumes the resulting ordered
physical trace through the
[unified substrate](../decisions/ddr4-pud-unified-substrate.md);
Ramulator does not interpret GEMV or hold functional payload values.

The [Accepted completion boundary](../decisions/mimdram-substrate-and-movement-request-boundary.md)
places GPU/host readout, conversion, and final arithmetic outside PuD substrate
timing. The programming model does not assign these costs. Functional
composition validation must follow this complete graph for each explicit
profile, without claiming complete OFP8 arithmetic beyond the operation
generator's documented scope.

## Prototype placement and physical trace contract

Build, generation, and execution instructions are in the
[DDR4 PuD user guide](../ddr4-pud-user-guide.md#gemv-trace-generation-and-execution).

The deterministic layout uses one rank, chip-local mats beginning at logical
mat zero, and disjoint output row bands within subarrays. Each band holds all
of that output's input domains, its three eight-row macro workspaces, protected
constants, and its generated micro-operation-level maximum. It rejects layouts
exceeding that static capacity; there is no runtime row allocator. Inputs and
constants are assumed preplaced. The JSON records their row locations, macro
workspaces, private PuD micro-operation-level temporary rows, domain sinks/residual rows, and one-based
physical completion indices for GPU readout before workspace reuse. Each
`completion_index` identifies a Request in the flattened physical sequence,
excluding headers and chain directives; it is not a concurrent completion
counter or a global barrier. Those indices describe the existing external
completion boundary, not simulated host requests or host timing.

The value-free trace schema is:

```text
PUD_TRACE
PROFILE <existing PlacementProfile.name>
RANKS <configured rank count>
CHAIN <id>
<compute opcode> channel rank bank_group bank first_mat last_mat row...
LC-MOV channel rank bank_group bank first_mat last_mat source_row source_group destination_row destination_group
GB-MOV channel rank bank_group bank source_mat destination_mat source_row source_group destination_row destination_group
```

`CHAIN` selects an opaque nonnegative integer ID (0 through 2147483647).
Subsequent physical requests append to that chain in file order until another
selection; selecting an existing ID resumes the same chain. IDs need not be
consecutive, and empty chains are allowed. A `CHAIN` selection is mandatory
before any physical Request. There is no implicit chain.

The GEMV writer emits one chain per output, numbered from zero, containing all
of that output's domains and the unchanged physical Request sequence. This
mapping belongs to the generator: PuDTrace does not interpret IDs as outputs,
arithmetic formats, resources, or Request source IDs. There are no cross-chain
dependencies. Producers must place all mutually dependent requests in the same
chain; the frontend does not infer dependencies from addresses. The layout and
its physical indices/counts remain unchanged.

Compute opcodes are `RowCopy`, `MAJ3`, `MAJ5`, `NOT`, and `NOT_COPY`,
with the existing ordered operand counts and semantics. All integers are
decimal; rows are full bank row IDs in `ExternalRow`, mat bounds are inclusive
logical IDs, and group selectors are `Group` identities rather than byte
addresses or arbitrary columns. Compute scopes cover whole mat rows. LC uses
the same range at both endpoints; GB uses singleton directed neighbors.
Physical requests contain no arithmetic format field: separate macro/profile
identities and generated arithmetic remain explicit in the generator/layout,
while Ramulator sees only their fully lowered primitive streams.

The `PuDTrace` frontend checks profile/rank agreement, resolves operands through the
installed resolver, supplies the existing compute transaction size or movement
N/A size, and allows at most one outstanding Request per chain. Only the full
completion/recovery callback releases that chain's successor. Different ready
chains may overlap. A FIFO ready queue starts in first-selection order; failed
sends rotate to its tail with the same Request at the chain head, and completed
chains with remaining work join the tail. There is at most one send attempt per
frontend tick, matching the existing load/store trace convention. The frontend
finishes only after all requests complete. It adds no controller scheduling or
compute/movement timing. Request completion and command occurrence counters
report full stream execution; `physical_requests_peak_inflight` counts the
peak accepted but not yet completed Requests, including queued/recovering work.

[Focused composition checks](../../../tools/pud_gemv_generator/test_integration.py)
use existing physical arithmetic replay, with movement effects outside Ramulator.
[Frontend checks](../../../tests/unit_tests/test_pud_gemv_frontend.py) reuse the
existing simulator setup and command recorder. Neither repeats exhaustive
arithmetic or the broad substrate regression matrix.

Controller cycles now model concurrent execution of the generated PuD physical
Request stream. They are **not full end-to-end GEMV latency**: GPU launch and
x duplication, transposition, readout/conversion, and GPU residual/domain final
combination remain outside this timing boundary. External domain readout before
workspace reuse still has no modeled cost. Static placement capacity and the
accepted engine, mat, subarray, Bank movement, command-bus and timing constraints
remain authoritative. A peak above one establishes outstanding-request overlap,
not necessarily simultaneous command execution on conflicting resources. See the
[chain execution plan](../plans/pud-gemv-chain-execution-plan.md) for timing evidence.

Layout metadata schema 2 names the scopes explicitly:
`micro_operation_requirements`, `micro_operation_counts`,
`micro_operation_temporary_rows_per_mat`, per-output
`micro_operation_temporary_rows`, and `macro_operation_temporary_row_bases`.
`PhysicalRowLayout.temporary_rows` supplies the exact statically selected set of
PuD micro-operation-level temporary rows: its length must equal the generated
`additional_temporary_rows`; insufficient and excess selections are rejected.
