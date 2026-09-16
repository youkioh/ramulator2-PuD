#include <stdint.h>
#include <stddef.h>
#include <cuda_runtime.h>

/*
 * Generated from tools/pud_operation_generator.
 *
 * These macros are micro-operation-level physical-row requirements obtained after
 * compiling/lowering each PuD operation. They are not handwritten constants.
 */
#include "generated/pud_operation_requirements.h"


/* -------------------------------------------------------------------------- */
/* GPU-PuD baseline configuration                                             */
/* -------------------------------------------------------------------------- */

#define MAT_SIZE                    512
#define MATS_PER_REDUCTION_DOMAIN  16   /* DDR4 baseline: one chip */
#define HFFS_PER_MAT                4

/*
 * Accepted GEMV domain: N > 0 and N % HFFS_PER_MAT == 0.
 * N need not be divisible by MAT_SIZE; partial final mats (e.g. N=516)
 * remain supported. No partial-group movement, masking, padding, or host
 * tail fallback is provided. These are preconditions of all six baseline/format macros.
 */

#define ELEMENTS_PER_REDUCTION_DOMAIN \
    (MAT_SIZE * MATS_PER_REDUCTION_DOMAIN)

/*
 * Exactly two active evaluation schedules, each with INT8/E4M3/E5M2 kernels:
 * MIMDRAM-InterMatFirst and MIMDRAM-IntraMatFirst.
 *
 * Common static physical placement, fastest to slowest:
 * bank -> bank group -> legal K-mat range slot -> chip -> subarray -> row band.
 * All banks consume a slot before another same-bank slot. Chip-local ranges
 * follow the existing resolver's directed edges. An output reserves maximum
 * domain K; each domain uses its prefix. Subarrays are capacity fallback only;
 * same-bank cross-subarray execution is serialized (no SALP).
 *
 * Mat indices in this specification are domain-local positions. The generator
 * translates them to the output's reserved physical range and context. No
 * different outputs share a ranged operation. External GPU completion costs
 * remain outside PuD timing. FP8 graphs are validated separately per schedule;
 * equality between schedules and numerical-accuracy evaluation are not required.
 */
enum PudGemvBaseline {
    MIMDRAM_InterMatFirst,
    MIMDRAM_IntraMatFirst
};

#define THREADS_PER_BLOCK           256

#define CEIL_DIV(a, b) (((a) + (b) - 1) / (b))
#define MIN(a, b)      ((a) < (b) ? (a) : (b))
#define MAX(a, b)      ((a) > (b) ? (a) : (b))

/*
 * Same-mat PuD micro-operations are serialized in this baseline.
 * Therefore one macro needs only the peak, not the sum, of the temporary-row
 * requirements of the micro-operations it uses.
 *
 * These are physical micro-operation-level temporary-row requirements. The compiler/
 * OS placement layer reserves these rows in the selected mat range. They are
 * not GPU-visible objects, are not cudaMalloc'ed, and do not need pud_obj_init().
 */
#define PUD_GEMV_INT8_OP_TMP_ROWS \
    MAX(PUD_INT8_MUL_TMP_ROWS, PUD_INT8_ADD_TMP_ROWS)

#define PUD_GEMV_FP8_E4M3_OP_TMP_ROWS \
    MAX(PUD_FP8_E4M3_MUL_TMP_ROWS, PUD_FP8_E4M3_ADD_TMP_ROWS)

#define PUD_GEMV_FP8_E5M2_OP_TMP_ROWS \
    MAX(PUD_FP8_E5M2_MUL_TMP_ROWS, PUD_FP8_E5M2_ADD_TMP_ROWS)


/* -------------------------------------------------------------------------- */
/* FP8 representations                                                       */
/* -------------------------------------------------------------------------- */

/*
 * Raw 8-bit FP encodings.
 *
 * E4M3 and E5M2 are intentionally exposed as separate PuD operation types and
 * APIs. They share an 8-bit storage width, but their arithmetic semantics are
 * distinct and are provided by separate pud_operation_generator profiles.
 */
typedef uint8_t pud_fp8_e4m3_t;
typedef uint8_t pud_fp8_e5m2_t;


/* -------------------------------------------------------------------------- */
/* GPU-PuD programming-model interfaces                                       */
/* -------------------------------------------------------------------------- */

/*
 * pud_obj_init() marks a GPU-visible allocated object as a PuD object.
 * The memory-controller-side data transposition unit transparently converts
 * between the normal GPU-visible layout and the bitslice layout in DRAM.
 *
 * PuD micro-operation-level temporary rows are compiler/OS-managed physical rows,
 * not GPU-visible objects, so they do not use this interface.
 */
void pud_obj_init(
    void *ptr,
    size_t element_count,
    size_t element_size
);


/*
 * Element-wise PuD INT8 multiplication.
 *
 * Public boundary:
 *     INT8 x INT8 -> INT8
 *
 * Internally, the prior-work-faithful baseline computes the complete signed
 * 16-bit product. Only the low 8 result bits are visible to the caller; high
 * product bits are still computed but are not exported as operation outputs.
 */
__device__
void pud_vector_mul_int8(
    const int8_t *src_a,
    const int8_t *src_b,
    int8_t *dst,
    int element_count,
    int mat_begin,
    int mat_end
);


/*
 * Element-wise PuD INT8 addition.
 *
 * Public boundary:
 *     INT8 + INT8 -> INT8
 *
 * The internal carry/high result is computed by the baseline operation, but
 * only the low 8 result bits are exported.
 */
__device__
void pud_vector_add_int8(
    const int8_t *src_a,
    const int8_t *src_b,
    int8_t *dst,
    int element_count,
    int mat_begin,
    int mat_end
);


/*
 * Element-wise PuD FP8 E4M3 multiplication/addition.
 *
 * These use the E4M3 arithmetic semantics already defined and validated by
 * tools/pud_operation_generator. No separate PuD FMA is used.
 */
__device__
void pud_vector_mul_fp8_e4m3(
    const pud_fp8_e4m3_t *src_a,
    const pud_fp8_e4m3_t *src_b,
    pud_fp8_e4m3_t *dst,
    int element_count,
    int mat_begin,
    int mat_end
);

__device__
void pud_vector_add_fp8_e4m3(
    const pud_fp8_e4m3_t *src_a,
    const pud_fp8_e4m3_t *src_b,
    pud_fp8_e4m3_t *dst,
    int element_count,
    int mat_begin,
    int mat_end
);


/*
 * Element-wise PuD FP8 E5M2 multiplication/addition.
 *
 * These use the E5M2 arithmetic semantics already defined and validated by
 * tools/pud_operation_generator. No separate PuD FMA is used.
 */
__device__
void pud_vector_mul_fp8_e5m2(
    const pud_fp8_e5m2_t *src_a,
    const pud_fp8_e5m2_t *src_b,
    pud_fp8_e5m2_t *dst,
    int element_count,
    int mat_begin,
    int mat_end
);

__device__
void pud_vector_add_fp8_e5m2(
    const pud_fp8_e5m2_t *src_a,
    const pud_fp8_e5m2_t *src_b,
    pud_fp8_e5m2_t *dst,
    int element_count,
    int mat_begin,
    int mat_end
);


/*
 * Logical PuD data movement.
 *
 * The macro generator resolves this to LC-MOV for same-mat movement or GB-MOV
 * for a legal forward neighboring-mat movement.
 */
__device__
void pud_mov(
    const void *src,
    int src_offset,
    void *dst,
    int dst_offset,
    int element_count,
    size_t element_size
);


/*
 * GPU-side scalar FP8 adds used only for the final <= HFFS_PER_MAT residual
 * combination. Each follows the same numerical semantics as its PuD ADD
 * operation profile.
 */
__device__
pud_fp8_e4m3_t pud_fp8_e4m3_scalar_add(
    pud_fp8_e4m3_t a,
    pud_fp8_e4m3_t b
);

__device__
pud_fp8_e5m2_t pud_fp8_e5m2_scalar_add(
    pud_fp8_e5m2_t a,
    pud_fp8_e5m2_t b
);


/*
 * Logical same-mat slice repeated over ONE output's inclusive mat range.
 * Offsets and element_count are mat-local and common to every selected mat.
 * This is a spelling of existing ranged LC-MOV, not a new DRAM primitive:
 * lower each bit plane / complete HFF group to one ranged LC Request. Each
 * mat copies its own source to its own destination, preserving other cells.
 * The compiler/OS maps these workspace bases to the same local rows throughout
 * this output's range. Ranged operations are confined to one GEMV output.
 */
__device__
void pud_mov_inside_mat_range(
    const void *src,
    int src_local_offset,
    void *dst,
    int dst_local_offset,
    int element_count,
    size_t element_size,
    int mat_begin,
    int mat_end
);


/* -------------------------------------------------------------------------- */
/* Input duplication                                                         */
/* -------------------------------------------------------------------------- */

/*
 * Duplicate x once for every GEMV output:
 *
 *     x_duplicated[i][j] = x[j]
 *
 * This explicitly provides an independent x copy for every dot product.
 * A future compiler/runtime may generate this duplication automatically.
 */
__global__
void duplicate_x_int8(
    const int8_t *x,
    int8_t *x_duplicated,
    int M,
    int N
)
{
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int total_elements = M * N;

    if (idx >= total_elements)
        return;

    x_duplicated[idx] = x[idx % N];
}


__global__
void duplicate_x_fp8_e4m3(
    const pud_fp8_e4m3_t *x,
    pud_fp8_e4m3_t *x_duplicated,
    int M,
    int N
)
{
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int total_elements = M * N;

    if (idx >= total_elements)
        return;

    x_duplicated[idx] = x[idx % N];
}


__global__
void duplicate_x_fp8_e5m2(
    const pud_fp8_e5m2_t *x,
    pud_fp8_e5m2_t *x_duplicated,
    int M,
    int N
)
{
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int total_elements = M * N;

    if (idx >= total_elements)
        return;

    x_duplicated[idx] = x[idx % N];
}


/* Largest power of two <= x. */
__device__
int floor_power_of_two(int x)
{
    int p = 1;

    while ((p << 1) <= x)
        p <<= 1;

    return p;
}


__device__
int8_t wrap_add_int8(
    int8_t a,
    int8_t b
)
{
    uint8_t ua = (uint8_t)a;
    uint8_t ub = (uint8_t)b;
    return (int8_t)(uint8_t)(ua + ub);
}


/* -------------------------------------------------------------------------- */
/* Temporary-row ownership                                                   */
/* -------------------------------------------------------------------------- */

/*
 * Two temporary-row scopes are used.
 *
 * 1. PuD macro-operation-level temporary rows
 *    - remain live across multiple PuD operations in one GEMV macro;
 *    - hold products/partial sums, alternate reduction outputs, and movement
 *      destinations;
 *    - are explicitly represented by the three macro workspaces below and are
 *      allocated before kernel launch.
 *
 * 2. PuD micro-operation-level temporary rows
 *    - are private to one lowered ADD/MUL operation;
 *    - their required count is generated by tools/pud_operation_generator;
 *    - the compiler/OS placement layer reserves the required physical local
 *      rows, and the operation lowerer maps primitives onto them;
 *    - they are reused by sequential micro-operations on the same mat and are
 *      not exposed as kernel arguments.
 *
 * The three macro-operation-level workspaces are intentionally distinct because the
 * current physical-lowering contract requires an ADD/MUL output to use rows
 * distinct from its input rows.
 */


/* -------------------------------------------------------------------------- */
/* Intra-mat reduction                                                       */
/* -------------------------------------------------------------------------- */

/*
 * Reduce one mat-local vector to at most HFFS_PER_MAT values.
 *
 * current_rows   : current reduction values
 * alternate_rows : distinct destination rows for the next ADD stage
 * movement_rows  : LC-MOV destination rows
 *
 * The helper ping-pongs current/alternate rows so no PuD ADD writes directly
 * onto one of its input row sets.
 */
__device__
int8_t *pud_reduce_inside_mat_int8(
    int8_t *current_rows,
    int8_t *alternate_rows,
    int8_t *movement_rows,
    int valid_count,
    int mat_idx,
    int *remaining_out
)
{
    int mat_offset = mat_idx * MAT_SIZE;

    if ((valid_count & (valid_count - 1)) != 0) {
        int target_count = floor_power_of_two(valid_count);
        int extra_count = valid_count - target_count;

        pud_mov(
            current_rows,
            mat_offset + target_count,
            movement_rows,
            mat_offset,
            extra_count,
            sizeof(int8_t)
        );

        pud_vector_add_int8(
            current_rows   + mat_offset,
            movement_rows  + mat_offset,
            alternate_rows + mat_offset,
            extra_count,
            mat_idx,
            mat_idx
        );

        /*
         * Values not participating in the first irregular pairwise ADD remain
         * part of the next vector and are copied into the alternate row set.
         */
        if (target_count > extra_count) {
            pud_mov(
                current_rows,
                mat_offset + extra_count,
                alternate_rows,
                mat_offset + extra_count,
                target_count - extra_count,
                sizeof(int8_t)
            );
        }

        int8_t *swap = current_rows;
        current_rows = alternate_rows;
        alternate_rows = swap;
        valid_count = target_count;
    }

    while (valid_count > HFFS_PER_MAT) {
        int half = valid_count / 2;

        pud_mov(
            current_rows,
            mat_offset + half,
            movement_rows,
            mat_offset,
            half,
            sizeof(int8_t)
        );

        pud_vector_add_int8(
            current_rows   + mat_offset,
            movement_rows  + mat_offset,
            alternate_rows + mat_offset,
            half,
            mat_idx,
            mat_idx
        );

        int8_t *swap = current_rows;
        current_rows = alternate_rows;
        alternate_rows = swap;
        valid_count = half;
    }

    *remaining_out = valid_count;
    return current_rows;
}


__device__
pud_fp8_e4m3_t *pud_reduce_inside_mat_fp8_e4m3(
    pud_fp8_e4m3_t *current_rows,
    pud_fp8_e4m3_t *alternate_rows,
    pud_fp8_e4m3_t *movement_rows,
    int valid_count,
    int mat_idx,
    int *remaining_out
)
{
    int mat_offset = mat_idx * MAT_SIZE;

    if ((valid_count & (valid_count - 1)) != 0) {
        int target_count = floor_power_of_two(valid_count);
        int extra_count = valid_count - target_count;

        pud_mov(
            current_rows,
            mat_offset + target_count,
            movement_rows,
            mat_offset,
            extra_count,
            sizeof(pud_fp8_e4m3_t)
        );

        pud_vector_add_fp8_e4m3(
            current_rows   + mat_offset,
            movement_rows  + mat_offset,
            alternate_rows + mat_offset,
            extra_count,
            mat_idx,
            mat_idx
        );

        if (target_count > extra_count) {
            pud_mov(
                current_rows,
                mat_offset + extra_count,
                alternate_rows,
                mat_offset + extra_count,
                target_count - extra_count,
                sizeof(pud_fp8_e4m3_t)
            );
        }

        pud_fp8_e4m3_t *swap = current_rows;
        current_rows = alternate_rows;
        alternate_rows = swap;
        valid_count = target_count;
    }

    while (valid_count > HFFS_PER_MAT) {
        int half = valid_count / 2;

        pud_mov(
            current_rows,
            mat_offset + half,
            movement_rows,
            mat_offset,
            half,
            sizeof(pud_fp8_e4m3_t)
        );

        pud_vector_add_fp8_e4m3(
            current_rows   + mat_offset,
            movement_rows  + mat_offset,
            alternate_rows + mat_offset,
            half,
            mat_idx,
            mat_idx
        );

        pud_fp8_e4m3_t *swap = current_rows;
        current_rows = alternate_rows;
        alternate_rows = swap;
        valid_count = half;
    }

    *remaining_out = valid_count;
    return current_rows;
}


__device__
pud_fp8_e5m2_t *pud_reduce_inside_mat_fp8_e5m2(
    pud_fp8_e5m2_t *current_rows,
    pud_fp8_e5m2_t *alternate_rows,
    pud_fp8_e5m2_t *movement_rows,
    int valid_count,
    int mat_idx,
    int *remaining_out
)
{
    int mat_offset = mat_idx * MAT_SIZE;

    if ((valid_count & (valid_count - 1)) != 0) {
        int target_count = floor_power_of_two(valid_count);
        int extra_count = valid_count - target_count;

        pud_mov(
            current_rows,
            mat_offset + target_count,
            movement_rows,
            mat_offset,
            extra_count,
            sizeof(pud_fp8_e5m2_t)
        );

        pud_vector_add_fp8_e5m2(
            current_rows   + mat_offset,
            movement_rows  + mat_offset,
            alternate_rows + mat_offset,
            extra_count,
            mat_idx,
            mat_idx
        );

        if (target_count > extra_count) {
            pud_mov(
                current_rows,
                mat_offset + extra_count,
                alternate_rows,
                mat_offset + extra_count,
                target_count - extra_count,
                sizeof(pud_fp8_e5m2_t)
            );
        }

        pud_fp8_e5m2_t *swap = current_rows;
        current_rows = alternate_rows;
        alternate_rows = swap;
        valid_count = target_count;
    }

    while (valid_count > HFFS_PER_MAT) {
        int half = valid_count / 2;

        pud_mov(
            current_rows,
            mat_offset + half,
            movement_rows,
            mat_offset,
            half,
            sizeof(pud_fp8_e5m2_t)
        );

        pud_vector_add_fp8_e5m2(
            current_rows   + mat_offset,
            movement_rows  + mat_offset,
            alternate_rows + mat_offset,
            half,
            mat_idx,
            mat_idx
        );

        pud_fp8_e5m2_t *swap = current_rows;
        current_rows = alternate_rows;
        alternate_rows = swap;
        valid_count = half;
    }

    *remaining_out = valid_count;
    return current_rows;
}


/* -------------------------------------------------------------------------- */
/* GPU-PuD INT8 GEMV                                                         */
/* -------------------------------------------------------------------------- */

/*
 * y = A x
 *
 * A            : [M][N]
 * x_duplicated : [M][N]
 * y            : [M]
 *
 * Baseline mapping: one GPU thread -> one output y[i].
 *
 * Inter-mat reduction follows the Accepted forward topology:
 *
 *     lower mat -> higher neighboring mat -> ... -> highest reachable sink
 *
 * Same-mat PuD micro-operations are serialized.
 */
__global__
void pud_gemv_intermatfirst_int8(
    const int8_t *A,
    const int8_t *x_duplicated,
    int8_t *y,
    int M,
    int N,
    int8_t *tmp_row,
    int8_t *reduction_tmp_row,
    int8_t *movement_tmp_row,
    int temporary_elements_per_thread
)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;

    if (i >= M)
        return;

    int8_t *tmp_rows =
        tmp_row + i * temporary_elements_per_thread;

    int8_t *reduction_tmp_rows =
        reduction_tmp_row + i * temporary_elements_per_thread;

    int8_t *movement_tmp_rows =
        movement_tmp_row + i * temporary_elements_per_thread;

    const int reduction_domain_count =
        CEIL_DIV(N, ELEMENTS_PER_REDUCTION_DOMAIN);

    int8_t output_sum = 0;

    for (int domain = 0; domain < reduction_domain_count; domain++) {
        int domain_start =
            domain * ELEMENTS_PER_REDUCTION_DOMAIN;

        int elements_this_domain =
            MIN(N - domain_start, ELEMENTS_PER_REDUCTION_DOMAIN);

        int mats_this_domain =
            CEIL_DIV(elements_this_domain, MAT_SIZE);

        int last_mat_valid =
            elements_this_domain -
            (mats_this_domain - 1) * MAT_SIZE;

        const int8_t *A_segment =
            A + i * N + domain_start;

        const int8_t *x_segment =
            x_duplicated + i * N + domain_start;

        /*
         * 1. Element-wise multiplication.
         *
         * The operation generator computes the full internal INT8 product and
         * exports the visible low 8 bits into tmp_rows.
         */
        pud_vector_mul_int8(
            A_segment,
            x_segment,
            tmp_rows,
            elements_this_domain,
            0,
            mats_this_domain - 1
        );

        /*
         * 2. Inter-mat forward reduction.
         *
         * product rows hold the original mat-local products.
         * reduction_tmp_rows hold accumulated outputs.
         * movement_tmp_rows hold GB-MOV destinations.
         */
        int8_t *accumulator_rows = tmp_rows;

        for (int src_mat = 0;
             src_mat < mats_this_domain - 1;
             src_mat++) {

            int dst_mat = src_mat + 1;

            int src_offset = src_mat * MAT_SIZE;
            int dst_offset = dst_mat * MAT_SIZE;

            int dst_valid =
                (dst_mat == mats_this_domain - 1)
                    ? last_mat_valid
                    : MAT_SIZE;

            /*
             * For K>1, every source accumulator is MAT_SIZE elements wide.
             * Move it forward to the adjacent destination mat.
             */
            pud_mov(
                accumulator_rows,
                src_offset,
                movement_tmp_rows,
                dst_offset,
                MAT_SIZE,
                sizeof(int8_t)
            );

            /*
             * Add the destination mat's valid local product lanes.
             * Output uses a distinct macro-operation-level row set.
             */
            pud_vector_add_int8(
                tmp_rows                 + dst_offset,
                movement_tmp_rows        + dst_offset,
                reduction_tmp_rows       + dst_offset,
                dst_valid,
                dst_mat,
                dst_mat
            );

            /*
             * If the last destination mat is partial, the accumulator lanes
             * beyond dst_valid have no local product term. Preserve those
             * moved lanes unchanged in the output accumulator.
             */
            if (dst_valid < MAT_SIZE) {
                pud_mov(
                    movement_tmp_rows,
                    dst_offset + dst_valid,
                    reduction_tmp_rows,
                    dst_offset + dst_valid,
                    MAT_SIZE - dst_valid,
                    sizeof(int8_t)
                );
            }

            accumulator_rows = reduction_tmp_rows;
        }

        int sink_mat = mats_this_domain - 1;

        int sink_valid =
            (mats_this_domain == 1)
                ? last_mat_valid
                : MAT_SIZE;

        /*
         * For K=1, the sink is tmp_rows.
         * For K>1, the forward fold leaves the sink accumulator in
         * reduction_tmp_rows.
         */
        int8_t *sink_rows =
            (mats_this_domain == 1)
                ? tmp_rows
                : reduction_tmp_rows;

        int8_t *alternate_rows =
            (sink_rows == tmp_rows)
                ? reduction_tmp_rows
                : tmp_rows;

        /*
         * 3. Intra-mat reduction in the highest reachable sink mat.
         */
        int remaining = 0;

        sink_rows = pud_reduce_inside_mat_int8(
            sink_rows,
            alternate_rows,
            movement_tmp_rows,
            sink_valid,
            sink_mat,
            &remaining
        );

        /*
         * 4. GPU-side final reduction.
         *
         * MIMDRAM reduces to at most HFFS_PER_MAT values. The remaining values
         * and disconnected reduction-domain results are combined by the GPU.
         */
        int sink_offset = sink_mat * MAT_SIZE;
        int8_t domain_sum = 0;

        for (int k = 0; k < remaining; k++) {
            domain_sum =
                wrap_add_int8(
                    domain_sum,
                    sink_rows[sink_offset + k]
                );
        }

        output_sum =
            wrap_add_int8(output_sum, domain_sum);
    }

    y[i] = output_sum;
}


/* -------------------------------------------------------------------------- */
/* GPU-PuD FP8 E4M3 GEMV                                                   */
/* -------------------------------------------------------------------------- */

__global__
void pud_gemv_intermatfirst_fp8_e4m3(
    const pud_fp8_e4m3_t *A,
    const pud_fp8_e4m3_t *x_duplicated,
    pud_fp8_e4m3_t *y,
    int M,
    int N,
    pud_fp8_e4m3_t *tmp_row,
    pud_fp8_e4m3_t *reduction_tmp_row,
    pud_fp8_e4m3_t *movement_tmp_row,
    int temporary_elements_per_thread
)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;

    if (i >= M)
        return;

    pud_fp8_e4m3_t *tmp_rows =
        tmp_row + i * temporary_elements_per_thread;

    pud_fp8_e4m3_t *reduction_tmp_rows =
        reduction_tmp_row + i * temporary_elements_per_thread;

    pud_fp8_e4m3_t *movement_tmp_rows =
        movement_tmp_row + i * temporary_elements_per_thread;

    const int reduction_domain_count =
        CEIL_DIV(N, ELEMENTS_PER_REDUCTION_DOMAIN);

    pud_fp8_e4m3_t output_sum = 0x00;

    for (int domain = 0; domain < reduction_domain_count; domain++) {
        int domain_start =
            domain * ELEMENTS_PER_REDUCTION_DOMAIN;

        int elements_this_domain =
            MIN(N - domain_start, ELEMENTS_PER_REDUCTION_DOMAIN);

        int mats_this_domain =
            CEIL_DIV(elements_this_domain, MAT_SIZE);

        int last_mat_valid =
            elements_this_domain -
            (mats_this_domain - 1) * MAT_SIZE;

        const pud_fp8_e4m3_t *A_segment =
            A + i * N + domain_start;

        const pud_fp8_e4m3_t *x_segment =
            x_duplicated + i * N + domain_start;

        pud_vector_mul_fp8_e4m3(
            A_segment,
            x_segment,
            tmp_rows,
            elements_this_domain,
            0,
            mats_this_domain - 1
        );

        pud_fp8_e4m3_t *accumulator_rows = tmp_rows;

        for (int src_mat = 0;
             src_mat < mats_this_domain - 1;
             src_mat++) {

            int dst_mat = src_mat + 1;

            int src_offset = src_mat * MAT_SIZE;
            int dst_offset = dst_mat * MAT_SIZE;

            int dst_valid =
                (dst_mat == mats_this_domain - 1)
                    ? last_mat_valid
                    : MAT_SIZE;

            pud_mov(
                accumulator_rows,
                src_offset,
                movement_tmp_rows,
                dst_offset,
                MAT_SIZE,
                sizeof(pud_fp8_e4m3_t)
            );

            pud_vector_add_fp8_e4m3(
                tmp_rows                 + dst_offset,
                movement_tmp_rows        + dst_offset,
                reduction_tmp_rows       + dst_offset,
                dst_valid,
                dst_mat,
                dst_mat
            );

            if (dst_valid < MAT_SIZE) {
                pud_mov(
                    movement_tmp_rows,
                    dst_offset + dst_valid,
                    reduction_tmp_rows,
                    dst_offset + dst_valid,
                    MAT_SIZE - dst_valid,
                    sizeof(pud_fp8_e4m3_t)
                );
            }

            accumulator_rows = reduction_tmp_rows;
        }

        int sink_mat = mats_this_domain - 1;

        int sink_valid =
            (mats_this_domain == 1)
                ? last_mat_valid
                : MAT_SIZE;

        pud_fp8_e4m3_t *sink_rows =
            (mats_this_domain == 1)
                ? tmp_rows
                : reduction_tmp_rows;

        pud_fp8_e4m3_t *alternate_rows =
            (sink_rows == tmp_rows)
                ? reduction_tmp_rows
                : tmp_rows;

        int remaining = 0;

        sink_rows = pud_reduce_inside_mat_fp8_e4m3(
            sink_rows,
            alternate_rows,
            movement_tmp_rows,
            sink_valid,
            sink_mat,
            &remaining
        );

        int sink_offset = sink_mat * MAT_SIZE;
        pud_fp8_e4m3_t domain_sum = 0x00;

        for (int k = 0; k < remaining; k++) {
            domain_sum =
                pud_fp8_e4m3_scalar_add(
                    domain_sum,
                    sink_rows[sink_offset + k]
                );
        }

        output_sum =
            pud_fp8_e4m3_scalar_add(
                output_sum,
                domain_sum
            );
    }

    y[i] = output_sum;
}


/* -------------------------------------------------------------------------- */
/* GPU-PuD FP8 E5M2 GEMV                                                   */
/* -------------------------------------------------------------------------- */

__global__
void pud_gemv_intermatfirst_fp8_e5m2(
    const pud_fp8_e5m2_t *A,
    const pud_fp8_e5m2_t *x_duplicated,
    pud_fp8_e5m2_t *y,
    int M,
    int N,
    pud_fp8_e5m2_t *tmp_row,
    pud_fp8_e5m2_t *reduction_tmp_row,
    pud_fp8_e5m2_t *movement_tmp_row,
    int temporary_elements_per_thread
)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;

    if (i >= M)
        return;

    pud_fp8_e5m2_t *tmp_rows =
        tmp_row + i * temporary_elements_per_thread;

    pud_fp8_e5m2_t *reduction_tmp_rows =
        reduction_tmp_row + i * temporary_elements_per_thread;

    pud_fp8_e5m2_t *movement_tmp_rows =
        movement_tmp_row + i * temporary_elements_per_thread;

    const int reduction_domain_count =
        CEIL_DIV(N, ELEMENTS_PER_REDUCTION_DOMAIN);

    pud_fp8_e5m2_t output_sum = 0x00;

    for (int domain = 0; domain < reduction_domain_count; domain++) {
        int domain_start =
            domain * ELEMENTS_PER_REDUCTION_DOMAIN;

        int elements_this_domain =
            MIN(N - domain_start, ELEMENTS_PER_REDUCTION_DOMAIN);

        int mats_this_domain =
            CEIL_DIV(elements_this_domain, MAT_SIZE);

        int last_mat_valid =
            elements_this_domain -
            (mats_this_domain - 1) * MAT_SIZE;

        const pud_fp8_e5m2_t *A_segment =
            A + i * N + domain_start;

        const pud_fp8_e5m2_t *x_segment =
            x_duplicated + i * N + domain_start;

        pud_vector_mul_fp8_e5m2(
            A_segment,
            x_segment,
            tmp_rows,
            elements_this_domain,
            0,
            mats_this_domain - 1
        );

        pud_fp8_e5m2_t *accumulator_rows = tmp_rows;

        for (int src_mat = 0;
             src_mat < mats_this_domain - 1;
             src_mat++) {

            int dst_mat = src_mat + 1;

            int src_offset = src_mat * MAT_SIZE;
            int dst_offset = dst_mat * MAT_SIZE;

            int dst_valid =
                (dst_mat == mats_this_domain - 1)
                    ? last_mat_valid
                    : MAT_SIZE;

            pud_mov(
                accumulator_rows,
                src_offset,
                movement_tmp_rows,
                dst_offset,
                MAT_SIZE,
                sizeof(pud_fp8_e5m2_t)
            );

            pud_vector_add_fp8_e5m2(
                tmp_rows                 + dst_offset,
                movement_tmp_rows        + dst_offset,
                reduction_tmp_rows       + dst_offset,
                dst_valid,
                dst_mat,
                dst_mat
            );

            if (dst_valid < MAT_SIZE) {
                pud_mov(
                    movement_tmp_rows,
                    dst_offset + dst_valid,
                    reduction_tmp_rows,
                    dst_offset + dst_valid,
                    MAT_SIZE - dst_valid,
                    sizeof(pud_fp8_e5m2_t)
                );
            }

            accumulator_rows = reduction_tmp_rows;
        }

        int sink_mat = mats_this_domain - 1;

        int sink_valid =
            (mats_this_domain == 1)
                ? last_mat_valid
                : MAT_SIZE;

        pud_fp8_e5m2_t *sink_rows =
            (mats_this_domain == 1)
                ? tmp_rows
                : reduction_tmp_rows;

        pud_fp8_e5m2_t *alternate_rows =
            (sink_rows == tmp_rows)
                ? reduction_tmp_rows
                : tmp_rows;

        int remaining = 0;

        sink_rows = pud_reduce_inside_mat_fp8_e5m2(
            sink_rows,
            alternate_rows,
            movement_tmp_rows,
            sink_valid,
            sink_mat,
            &remaining
        );

        int sink_offset = sink_mat * MAT_SIZE;
        pud_fp8_e5m2_t domain_sum = 0x00;

        for (int k = 0; k < remaining; k++) {
            domain_sum =
                pud_fp8_e5m2_scalar_add(
                    domain_sum,
                    sink_rows[sink_offset + k]
                );
        }

        output_sum =
            pud_fp8_e5m2_scalar_add(
                output_sum,
                domain_sum
            );
    }

    y[i] = output_sum;
}



/* -------------------------------------------------------------------------- */
/* MIMDRAM-IntraMatFirst: local trees before residual-only forward merging     */
/* -------------------------------------------------------------------------- */

/*
 * Full mats in one output use identical seven local stages in one range.
 * A partial final mat uses the existing singleton irregular/tree helper.
 * ADD's element_count below is the consumed prefix PER selected mat; physical
 * arithmetic still covers full mat rows. Unconsumed lanes are not padded terms.
 */

__device__
int8_t *pud_reduce_full_mat_range_int8(
    int8_t *current_rows,
    int8_t *alternate_rows,
    int8_t *movement_rows,
    int mat_begin,
    int mat_end
)
{
    for (int valid = MAT_SIZE; valid > HFFS_PER_MAT; valid /= 2) {
        int half = valid / 2;
        pud_mov_inside_mat_range(current_rows, half, movement_rows, 0,
                                 half, sizeof(int8_t), mat_begin, mat_end);
        pud_vector_add_int8(
            current_rows + mat_begin * MAT_SIZE,
            movement_rows + mat_begin * MAT_SIZE,
            alternate_rows + mat_begin * MAT_SIZE,
            half, mat_begin, mat_end);
        int8_t *swap = current_rows;
        current_rows = alternate_rows;
        alternate_rows = swap;
    }
    return current_rows;
}

__global__
void pud_gemv_intramatfirst_int8(
    const int8_t *A,
    const int8_t *x_duplicated,
    int8_t *y,
    int M,
    int N,
    int8_t *tmp_row,
    int8_t *reduction_tmp_row,
    int8_t *movement_tmp_row,
    int temporary_elements_per_thread
)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= M)
        return;
    int8_t *primary = tmp_row + i * temporary_elements_per_thread;
    int8_t *reduction = reduction_tmp_row + i * temporary_elements_per_thread;
    int8_t *movement = movement_tmp_row + i * temporary_elements_per_thread;
    int8_t output_sum = 0;
    for (int domain = 0; domain < CEIL_DIV(N, ELEMENTS_PER_REDUCTION_DOMAIN); domain++) {
        int start = domain * ELEMENTS_PER_REDUCTION_DOMAIN;
        int elements = MIN(N - start, ELEMENTS_PER_REDUCTION_DOMAIN);
        int mats = CEIL_DIV(elements, MAT_SIZE);
        int full_mats = elements / MAT_SIZE;
        int last_valid = elements - (mats - 1) * MAT_SIZE;
        pud_vector_mul_int8(A + i * N + start, x_duplicated + i * N + start,
                                primary, elements, 0, mats - 1);

        int8_t *local_rows[MATS_PER_REDUCTION_DOMAIN];
        if (full_mats > 0) {
            int8_t *rows = pud_reduce_full_mat_range_int8(
                primary, reduction, movement, 0, full_mats - 1);
            for (int mat = 0; mat < full_mats; mat++)
                local_rows[mat] = rows;
        }
        int remaining = HFFS_PER_MAT;
        if (last_valid < MAT_SIZE) {
            local_rows[mats - 1] = pud_reduce_inside_mat_int8(
                primary, reduction, movement, last_valid, mats - 1, &remaining);
        }

        int8_t *accumulator = local_rows[0];
        for (int dst_mat = 1; dst_mat < mats; dst_mat++) {
            int dst_offset = dst_mat * MAT_SIZE;
            pud_mov(accumulator, (dst_mat - 1) * MAT_SIZE,
                    movement, dst_offset, remaining, sizeof(int8_t));
            int8_t *local = local_rows[dst_mat];
            int8_t *alternate = (local == primary) ? reduction : primary;
            pud_vector_add_int8(local + dst_offset, movement + dst_offset,
                                    alternate + dst_offset, remaining, dst_mat, dst_mat);
            accumulator = alternate;
        }
        int8_t domain_sum = 0;
        for (int lane = 0; lane < remaining; lane++)
            domain_sum = wrap_add_int8(domain_sum, accumulator[(mats - 1) * MAT_SIZE + lane]);
        output_sum = wrap_add_int8(output_sum, domain_sum);
    }
    y[i] = output_sum;
}


__device__
pud_fp8_e4m3_t *pud_reduce_full_mat_range_fp8_e4m3(
    pud_fp8_e4m3_t *current_rows,
    pud_fp8_e4m3_t *alternate_rows,
    pud_fp8_e4m3_t *movement_rows,
    int mat_begin,
    int mat_end
)
{
    for (int valid = MAT_SIZE; valid > HFFS_PER_MAT; valid /= 2) {
        int half = valid / 2;
        pud_mov_inside_mat_range(current_rows, half, movement_rows, 0,
                                 half, sizeof(pud_fp8_e4m3_t), mat_begin, mat_end);
        pud_vector_add_fp8_e4m3(
            current_rows + mat_begin * MAT_SIZE,
            movement_rows + mat_begin * MAT_SIZE,
            alternate_rows + mat_begin * MAT_SIZE,
            half, mat_begin, mat_end);
        pud_fp8_e4m3_t *swap = current_rows;
        current_rows = alternate_rows;
        alternate_rows = swap;
    }
    return current_rows;
}

__global__
void pud_gemv_intramatfirst_fp8_e4m3(
    const pud_fp8_e4m3_t *A,
    const pud_fp8_e4m3_t *x_duplicated,
    pud_fp8_e4m3_t *y,
    int M,
    int N,
    pud_fp8_e4m3_t *tmp_row,
    pud_fp8_e4m3_t *reduction_tmp_row,
    pud_fp8_e4m3_t *movement_tmp_row,
    int temporary_elements_per_thread
)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= M)
        return;
    pud_fp8_e4m3_t *primary = tmp_row + i * temporary_elements_per_thread;
    pud_fp8_e4m3_t *reduction = reduction_tmp_row + i * temporary_elements_per_thread;
    pud_fp8_e4m3_t *movement = movement_tmp_row + i * temporary_elements_per_thread;
    pud_fp8_e4m3_t output_sum = 0;
    for (int domain = 0; domain < CEIL_DIV(N, ELEMENTS_PER_REDUCTION_DOMAIN); domain++) {
        int start = domain * ELEMENTS_PER_REDUCTION_DOMAIN;
        int elements = MIN(N - start, ELEMENTS_PER_REDUCTION_DOMAIN);
        int mats = CEIL_DIV(elements, MAT_SIZE);
        int full_mats = elements / MAT_SIZE;
        int last_valid = elements - (mats - 1) * MAT_SIZE;
        pud_vector_mul_fp8_e4m3(A + i * N + start, x_duplicated + i * N + start,
                                primary, elements, 0, mats - 1);

        pud_fp8_e4m3_t *local_rows[MATS_PER_REDUCTION_DOMAIN];
        if (full_mats > 0) {
            pud_fp8_e4m3_t *rows = pud_reduce_full_mat_range_fp8_e4m3(
                primary, reduction, movement, 0, full_mats - 1);
            for (int mat = 0; mat < full_mats; mat++)
                local_rows[mat] = rows;
        }
        int remaining = HFFS_PER_MAT;
        if (last_valid < MAT_SIZE) {
            local_rows[mats - 1] = pud_reduce_inside_mat_fp8_e4m3(
                primary, reduction, movement, last_valid, mats - 1, &remaining);
        }

        pud_fp8_e4m3_t *accumulator = local_rows[0];
        for (int dst_mat = 1; dst_mat < mats; dst_mat++) {
            int dst_offset = dst_mat * MAT_SIZE;
            pud_mov(accumulator, (dst_mat - 1) * MAT_SIZE,
                    movement, dst_offset, remaining, sizeof(pud_fp8_e4m3_t));
            pud_fp8_e4m3_t *local = local_rows[dst_mat];
            pud_fp8_e4m3_t *alternate = (local == primary) ? reduction : primary;
            pud_vector_add_fp8_e4m3(local + dst_offset, movement + dst_offset,
                                    alternate + dst_offset, remaining, dst_mat, dst_mat);
            accumulator = alternate;
        }
        pud_fp8_e4m3_t domain_sum = 0;
        for (int lane = 0; lane < remaining; lane++)
            domain_sum = pud_fp8_e4m3_scalar_add(domain_sum, accumulator[(mats - 1) * MAT_SIZE + lane]);
        output_sum = pud_fp8_e4m3_scalar_add(output_sum, domain_sum);
    }
    y[i] = output_sum;
}


__device__
pud_fp8_e5m2_t *pud_reduce_full_mat_range_fp8_e5m2(
    pud_fp8_e5m2_t *current_rows,
    pud_fp8_e5m2_t *alternate_rows,
    pud_fp8_e5m2_t *movement_rows,
    int mat_begin,
    int mat_end
)
{
    for (int valid = MAT_SIZE; valid > HFFS_PER_MAT; valid /= 2) {
        int half = valid / 2;
        pud_mov_inside_mat_range(current_rows, half, movement_rows, 0,
                                 half, sizeof(pud_fp8_e5m2_t), mat_begin, mat_end);
        pud_vector_add_fp8_e5m2(
            current_rows + mat_begin * MAT_SIZE,
            movement_rows + mat_begin * MAT_SIZE,
            alternate_rows + mat_begin * MAT_SIZE,
            half, mat_begin, mat_end);
        pud_fp8_e5m2_t *swap = current_rows;
        current_rows = alternate_rows;
        alternate_rows = swap;
    }
    return current_rows;
}

__global__
void pud_gemv_intramatfirst_fp8_e5m2(
    const pud_fp8_e5m2_t *A,
    const pud_fp8_e5m2_t *x_duplicated,
    pud_fp8_e5m2_t *y,
    int M,
    int N,
    pud_fp8_e5m2_t *tmp_row,
    pud_fp8_e5m2_t *reduction_tmp_row,
    pud_fp8_e5m2_t *movement_tmp_row,
    int temporary_elements_per_thread
)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= M)
        return;
    pud_fp8_e5m2_t *primary = tmp_row + i * temporary_elements_per_thread;
    pud_fp8_e5m2_t *reduction = reduction_tmp_row + i * temporary_elements_per_thread;
    pud_fp8_e5m2_t *movement = movement_tmp_row + i * temporary_elements_per_thread;
    pud_fp8_e5m2_t output_sum = 0;
    for (int domain = 0; domain < CEIL_DIV(N, ELEMENTS_PER_REDUCTION_DOMAIN); domain++) {
        int start = domain * ELEMENTS_PER_REDUCTION_DOMAIN;
        int elements = MIN(N - start, ELEMENTS_PER_REDUCTION_DOMAIN);
        int mats = CEIL_DIV(elements, MAT_SIZE);
        int full_mats = elements / MAT_SIZE;
        int last_valid = elements - (mats - 1) * MAT_SIZE;
        pud_vector_mul_fp8_e5m2(A + i * N + start, x_duplicated + i * N + start,
                                primary, elements, 0, mats - 1);

        pud_fp8_e5m2_t *local_rows[MATS_PER_REDUCTION_DOMAIN];
        if (full_mats > 0) {
            pud_fp8_e5m2_t *rows = pud_reduce_full_mat_range_fp8_e5m2(
                primary, reduction, movement, 0, full_mats - 1);
            for (int mat = 0; mat < full_mats; mat++)
                local_rows[mat] = rows;
        }
        int remaining = HFFS_PER_MAT;
        if (last_valid < MAT_SIZE) {
            local_rows[mats - 1] = pud_reduce_inside_mat_fp8_e5m2(
                primary, reduction, movement, last_valid, mats - 1, &remaining);
        }

        pud_fp8_e5m2_t *accumulator = local_rows[0];
        for (int dst_mat = 1; dst_mat < mats; dst_mat++) {
            int dst_offset = dst_mat * MAT_SIZE;
            pud_mov(accumulator, (dst_mat - 1) * MAT_SIZE,
                    movement, dst_offset, remaining, sizeof(pud_fp8_e5m2_t));
            pud_fp8_e5m2_t *local = local_rows[dst_mat];
            pud_fp8_e5m2_t *alternate = (local == primary) ? reduction : primary;
            pud_vector_add_fp8_e5m2(local + dst_offset, movement + dst_offset,
                                    alternate + dst_offset, remaining, dst_mat, dst_mat);
            accumulator = alternate;
        }
        pud_fp8_e5m2_t domain_sum = 0;
        for (int lane = 0; lane < remaining; lane++)
            domain_sum = pud_fp8_e5m2_scalar_add(domain_sum, accumulator[(mats - 1) * MAT_SIZE + lane]);
        output_sum = pud_fp8_e5m2_scalar_add(output_sum, domain_sum);
    }
    y[i] = output_sum;
}

/* -------------------------------------------------------------------------- */
/* Example host setup                                                        */
/* -------------------------------------------------------------------------- */

int main()
{
    /* Select either explicit baseline; each launch below names its schedule. */
    const PudGemvBaseline baseline = MIMDRAM_InterMatFirst;
    /*
     * Attention-score GEMV during decode.
     *
     * M = sequence length
     * N = head dimension
     */
    const int M = 2048;
    const int N = 128;

    const int total_mats =
        CEIL_DIV(N, MAT_SIZE);

    const int temporary_mats_per_thread =
        MIN(total_mats, MATS_PER_REDUCTION_DOMAIN);

    const int temporary_elements_per_thread =
        temporary_mats_per_thread * MAT_SIZE;

    const int total_elements =
        M * N;

    const int duplication_blocks =
        CEIL_DIV(total_elements, THREADS_PER_BLOCK);

    const int gemv_blocks =
        CEIL_DIV(M, THREADS_PER_BLOCK);


    /* ---------------------------------------------------------------------- */
    /* INT8 example                                                           */
    /* ---------------------------------------------------------------------- */

    int8_t *A_int8;
    int8_t *x_int8;
    int8_t *x_duplicated_int8;
    int8_t *y_int8;

    int8_t *temporary_row_workspace_int8;
    int8_t *reduction_temporary_row_workspace_int8;
    int8_t *movement_temporary_row_workspace_int8;

    cudaMalloc(&A_int8, M * N * sizeof(int8_t));
    cudaMalloc(&x_int8, N * sizeof(int8_t));
    cudaMalloc(&x_duplicated_int8, M * N * sizeof(int8_t));
    cudaMalloc(&y_int8, M * sizeof(int8_t));

    cudaMalloc(
        &temporary_row_workspace_int8,
        M * temporary_elements_per_thread * sizeof(int8_t)
    );

    cudaMalloc(
        &reduction_temporary_row_workspace_int8,
        M * temporary_elements_per_thread * sizeof(int8_t)
    );

    cudaMalloc(
        &movement_temporary_row_workspace_int8,
        M * temporary_elements_per_thread * sizeof(int8_t)
    );

    pud_obj_init(
        A_int8,
        M * N,
        sizeof(int8_t)
    );

    pud_obj_init(
        x_duplicated_int8,
        M * N,
        sizeof(int8_t)
    );

    pud_obj_init(
        temporary_row_workspace_int8,
        M * temporary_elements_per_thread,
        sizeof(int8_t)
    );

    pud_obj_init(
        reduction_temporary_row_workspace_int8,
        M * temporary_elements_per_thread,
        sizeof(int8_t)
    );

    pud_obj_init(
        movement_temporary_row_workspace_int8,
        M * temporary_elements_per_thread,
        sizeof(int8_t)
    );

    duplicate_x_int8<<<duplication_blocks, THREADS_PER_BLOCK>>>(
        x_int8,
        x_duplicated_int8,
        M,
        N
    );

    /*
     * PUD_GEMV_INT8_OP_TMP_ROWS is an additional physical-row placement
     * requirement handled by the compiler/OS; it is not passed as a kernel
     * pointer and is not initialized as a PuD object.
     */
    if (baseline == MIMDRAM_InterMatFirst) {
        pud_gemv_intermatfirst_int8<<<gemv_blocks, THREADS_PER_BLOCK>>>(
            A_int8,
            x_duplicated_int8,
            y_int8,
            M,
            N,
            temporary_row_workspace_int8,
            reduction_temporary_row_workspace_int8,
            movement_temporary_row_workspace_int8,
            temporary_elements_per_thread
        );
    } else {
        pud_gemv_intramatfirst_int8<<<gemv_blocks, THREADS_PER_BLOCK>>>(
            A_int8,
            x_duplicated_int8,
            y_int8,
            M,
            N,
            temporary_row_workspace_int8,
            reduction_temporary_row_workspace_int8,
            movement_temporary_row_workspace_int8,
            temporary_elements_per_thread
        );
    }


    /* ---------------------------------------------------------------------- */
    /* FP8 E4M3 example                                                      */
    /* ---------------------------------------------------------------------- */

    pud_fp8_e4m3_t *A_fp8_e4m3;
    pud_fp8_e4m3_t *x_fp8_e4m3;
    pud_fp8_e4m3_t *x_duplicated_fp8_e4m3;
    pud_fp8_e4m3_t *y_fp8_e4m3;

    pud_fp8_e4m3_t *temporary_row_workspace_fp8_e4m3;
    pud_fp8_e4m3_t *reduction_temporary_row_workspace_fp8_e4m3;
    pud_fp8_e4m3_t *movement_temporary_row_workspace_fp8_e4m3;

    cudaMalloc(&A_fp8_e4m3, M * N * sizeof(pud_fp8_e4m3_t));
    cudaMalloc(&x_fp8_e4m3, N * sizeof(pud_fp8_e4m3_t));
    cudaMalloc(&x_duplicated_fp8_e4m3, M * N * sizeof(pud_fp8_e4m3_t));
    cudaMalloc(&y_fp8_e4m3, M * sizeof(pud_fp8_e4m3_t));

    cudaMalloc(
        &temporary_row_workspace_fp8_e4m3,
        M * temporary_elements_per_thread * sizeof(pud_fp8_e4m3_t)
    );

    cudaMalloc(
        &reduction_temporary_row_workspace_fp8_e4m3,
        M * temporary_elements_per_thread * sizeof(pud_fp8_e4m3_t)
    );

    cudaMalloc(
        &movement_temporary_row_workspace_fp8_e4m3,
        M * temporary_elements_per_thread * sizeof(pud_fp8_e4m3_t)
    );

    pud_obj_init(A_fp8_e4m3, M * N, sizeof(pud_fp8_e4m3_t));
    pud_obj_init(x_duplicated_fp8_e4m3, M * N, sizeof(pud_fp8_e4m3_t));

    pud_obj_init(
        temporary_row_workspace_fp8_e4m3,
        M * temporary_elements_per_thread,
        sizeof(pud_fp8_e4m3_t)
    );

    pud_obj_init(
        reduction_temporary_row_workspace_fp8_e4m3,
        M * temporary_elements_per_thread,
        sizeof(pud_fp8_e4m3_t)
    );

    pud_obj_init(
        movement_temporary_row_workspace_fp8_e4m3,
        M * temporary_elements_per_thread,
        sizeof(pud_fp8_e4m3_t)
    );

    duplicate_x_fp8_e4m3<<<duplication_blocks, THREADS_PER_BLOCK>>>(
        x_fp8_e4m3,
        x_duplicated_fp8_e4m3,
        M,
        N
    );

    if (baseline == MIMDRAM_InterMatFirst) {
        pud_gemv_intermatfirst_fp8_e4m3<<<gemv_blocks, THREADS_PER_BLOCK>>>(
            A_fp8_e4m3,
            x_duplicated_fp8_e4m3,
            y_fp8_e4m3,
            M,
            N,
            temporary_row_workspace_fp8_e4m3,
            reduction_temporary_row_workspace_fp8_e4m3,
            movement_temporary_row_workspace_fp8_e4m3,
            temporary_elements_per_thread
        );
    } else {
        pud_gemv_intramatfirst_fp8_e4m3<<<gemv_blocks, THREADS_PER_BLOCK>>>(
            A_fp8_e4m3,
            x_duplicated_fp8_e4m3,
            y_fp8_e4m3,
            M,
            N,
            temporary_row_workspace_fp8_e4m3,
            reduction_temporary_row_workspace_fp8_e4m3,
            movement_temporary_row_workspace_fp8_e4m3,
            temporary_elements_per_thread
        );
    }


    /* ---------------------------------------------------------------------- */
    /* FP8 E5M2 example                                                      */
    /* ---------------------------------------------------------------------- */

    pud_fp8_e5m2_t *A_fp8_e5m2;
    pud_fp8_e5m2_t *x_fp8_e5m2;
    pud_fp8_e5m2_t *x_duplicated_fp8_e5m2;
    pud_fp8_e5m2_t *y_fp8_e5m2;

    pud_fp8_e5m2_t *temporary_row_workspace_fp8_e5m2;
    pud_fp8_e5m2_t *reduction_temporary_row_workspace_fp8_e5m2;
    pud_fp8_e5m2_t *movement_temporary_row_workspace_fp8_e5m2;

    cudaMalloc(&A_fp8_e5m2, M * N * sizeof(pud_fp8_e5m2_t));
    cudaMalloc(&x_fp8_e5m2, N * sizeof(pud_fp8_e5m2_t));
    cudaMalloc(&x_duplicated_fp8_e5m2, M * N * sizeof(pud_fp8_e5m2_t));
    cudaMalloc(&y_fp8_e5m2, M * sizeof(pud_fp8_e5m2_t));

    cudaMalloc(
        &temporary_row_workspace_fp8_e5m2,
        M * temporary_elements_per_thread * sizeof(pud_fp8_e5m2_t)
    );

    cudaMalloc(
        &reduction_temporary_row_workspace_fp8_e5m2,
        M * temporary_elements_per_thread * sizeof(pud_fp8_e5m2_t)
    );

    cudaMalloc(
        &movement_temporary_row_workspace_fp8_e5m2,
        M * temporary_elements_per_thread * sizeof(pud_fp8_e5m2_t)
    );

    pud_obj_init(A_fp8_e5m2, M * N, sizeof(pud_fp8_e5m2_t));
    pud_obj_init(x_duplicated_fp8_e5m2, M * N, sizeof(pud_fp8_e5m2_t));

    pud_obj_init(
        temporary_row_workspace_fp8_e5m2,
        M * temporary_elements_per_thread,
        sizeof(pud_fp8_e5m2_t)
    );

    pud_obj_init(
        reduction_temporary_row_workspace_fp8_e5m2,
        M * temporary_elements_per_thread,
        sizeof(pud_fp8_e5m2_t)
    );

    pud_obj_init(
        movement_temporary_row_workspace_fp8_e5m2,
        M * temporary_elements_per_thread,
        sizeof(pud_fp8_e5m2_t)
    );

    duplicate_x_fp8_e5m2<<<duplication_blocks, THREADS_PER_BLOCK>>>(
        x_fp8_e5m2,
        x_duplicated_fp8_e5m2,
        M,
        N
    );

    if (baseline == MIMDRAM_InterMatFirst) {
        pud_gemv_intermatfirst_fp8_e5m2<<<gemv_blocks, THREADS_PER_BLOCK>>>(
            A_fp8_e5m2,
            x_duplicated_fp8_e5m2,
            y_fp8_e5m2,
            M,
            N,
            temporary_row_workspace_fp8_e5m2,
            reduction_temporary_row_workspace_fp8_e5m2,
            movement_temporary_row_workspace_fp8_e5m2,
            temporary_elements_per_thread
        );
    } else {
        pud_gemv_intramatfirst_fp8_e5m2<<<gemv_blocks, THREADS_PER_BLOCK>>>(
            A_fp8_e5m2,
            x_duplicated_fp8_e5m2,
            y_fp8_e5m2,
            M,
            N,
            temporary_row_workspace_fp8_e5m2,
            reduction_temporary_row_workspace_fp8_e5m2,
            movement_temporary_row_workspace_fp8_e5m2,
            temporary_elements_per_thread
        );
    }

    cudaDeviceSynchronize();


    cudaFree(movement_temporary_row_workspace_fp8_e5m2);
    cudaFree(reduction_temporary_row_workspace_fp8_e5m2);
    cudaFree(temporary_row_workspace_fp8_e5m2);

    cudaFree(y_fp8_e5m2);
    cudaFree(x_duplicated_fp8_e5m2);
    cudaFree(x_fp8_e5m2);
    cudaFree(A_fp8_e5m2);


    cudaFree(movement_temporary_row_workspace_fp8_e4m3);
    cudaFree(reduction_temporary_row_workspace_fp8_e4m3);
    cudaFree(temporary_row_workspace_fp8_e4m3);

    cudaFree(y_fp8_e4m3);
    cudaFree(x_duplicated_fp8_e4m3);
    cudaFree(x_fp8_e4m3);
    cudaFree(A_fp8_e4m3);


    cudaFree(movement_temporary_row_workspace_int8);
    cudaFree(reduction_temporary_row_workspace_int8);
    cudaFree(temporary_row_workspace_int8);

    cudaFree(y_int8);
    cudaFree(x_duplicated_int8);
    cudaFree(x_int8);
    cudaFree(A_int8);

    return 0;
}
