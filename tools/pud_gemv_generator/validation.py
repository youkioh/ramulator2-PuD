"""Value-bearing composition checks outside Ramulator; reuse operation replay."""
from dataclasses import replace
from functools import lru_cache
from tools.pud_operation_generator.lowering import make_default_physical_layout, lower_to_physical
from tools.pud_operation_generator.lowering import LoweredPrimitive
from tools.pud_operation_generator.physical_replay import execute_physical
from tools.pud_operation_generator.fp8 import E4M3, E5M2, fp8_add_reference, scalar_fp8_mul_reference
from tools.pud_operation_generator.requirements import BUILDERS
from .generator import PROFILES, placement_profile


def scalar_operations(profile):
    if profile == "int8-gemv":
        return lambda a, b: (a+b) & 255, lambda a, b: (a*b) & 255
    format_ = {"fp8-e4m3-gemv": E4M3, "fp8-e5m2-gemv": E5M2}[profile]

    @lru_cache(None)
    def add(a, b):
        fields = fp8_add_reference(a, b, format_)
        # Existing ADD exports low exponent bits outside its comparison domain.
        # This is raw graph equality, not a new IEEE FP8 numerical policy.
        return ((fields["result_sign"] << 7) |
                ((fields["exponent"] & format_.exponent_mask) << format_.fraction_bits) |
                fields["fraction"])
    return add, lambda a, b: scalar_fp8_mul_reference(a, b, format_)


def scalar_graph(profile, matrix, vector):
    """The .cu scalar MUL/ADD graph, independently over lists of valid terms."""
    add, mul = scalar_operations(profile)
    geometry = placement_profile()
    width, h = geometry["cells_per_mat_row"], geometry["hffs_per_mat"]
    domain_size = width * geometry["mats_per_chip"]
    results = []
    for row in matrix:
        output_sum = 0
        for start in range(0, len(vector), domain_size):
            products = [mul(a, x) for a, x in zip(
                row[start:start+domain_size], vector[start:start+domain_size])]
            accumulator = products[:width]
            for offset in range(width, len(products), width):
                local = products[offset:offset+width]
                accumulator = [add(v, accumulator[i]) for i, v in enumerate(local)] + accumulator[len(local):]
            target = 1 << (len(accumulator).bit_length()-1)
            if target != len(accumulator):
                extra = len(accumulator)-target
                accumulator = [add(accumulator[i], accumulator[target+i]) for i in range(extra)] + accumulator[extra:target]
            while len(accumulator) > h:
                half = len(accumulator)//2
                accumulator = [add(accumulator[i], accumulator[half+i]) for i in range(half)]
            domain_sum = 0
            for value in accumulator:
                domain_sum = add(domain_sum, value)
            output_sum = add(output_sum, domain_sum)
        results.append(output_sum)
    return results


def execute_trace(metadata, trace, matrix, vector, poison=0xA5):
    """Replay physical lines, snapshotting .cu host readout at each domain.

    Unused cells begin with arbitrary test data, not zero-padded GEMV terms.
    No payload state enters Ramulator.
    """
    geometry = placement_profile()
    width, h = geometry["cells_per_mat_row"], geometry["hffs_per_mat"]
    columns = geometry["group_position_to_column"]
    column = lambda lane: columns[lane]
    mask = (1 << width)-1
    if len(matrix) != metadata["M"] or len(vector) != metadata["N"] or any(len(r) != len(vector) for r in matrix):
        raise ValueError("input shape differs from GEMV layout")
    memory, events = {}, {}
    program = BUILDERS[PROFILES[metadata["macro_profile"]][0]]()
    bits = next(iter(metadata["micro_operation_requirements"].values()))["output_rows"]
    for output, record in enumerate(metadata["outputs"]):
        context = tuple(record["context"])
        start = 0
        for domain_index, domain in enumerate(record["domains"]):
            a_row, x_row = record["input_rows"][domain_index]
            for local_mat in range(domain["mat_count"]):
                mat = domain["mat_begin"] + local_mat
                rows = memory.setdefault((*context, mat), {})
                for first in record["macro_operation_temporary_row_bases"].values():
                    for bit in range(bits):
                        rows[first+bit] = mask if (poison >> bit) & 1 else 0
                for name, row_id in record["constant_rows"].items():
                    rows[row_id] = mask if name == program.one else 0
                valid = min(width, domain["elements"]-local_mat*width)
                for first, values in ((a_row, matrix[output]), (x_row, vector)):
                    for bit in range(bits):
                        word = mask if (poison >> bit) & 1 else 0
                        for lane in range(valid):
                            pos = column(lane)
                            word = (word & ~(1 << pos)) | (((values[start+local_mat*width+lane] >> bit) & 1) << pos)
                        rows[first+bit] = word
            events[domain["completion_index"]] = (output, context, domain)
            start += domain["elements"]

    template = replace(lower_to_physical(program, make_default_physical_layout(program)),
                       designated_inputs=(), designated_constants=(), result_bindings=(),
                       local_row_count=geometry["rows_per_bank"])
    add, _ = scalar_operations(metadata["macro_profile"])
    results = [0] * metadata["M"]
    for index, line in enumerate(trace, 1):
        opcode, *values = line.split()
        ch, rank, bg, bank, first, last, *operands = map(int, values)
        context = (ch, rank, bg, bank)
        if opcode in ("LC-MOV", "GB-MOV"):
            src, src_group, dst, dst_group = operands
            source, destination = memory[(*context, first)], memory[(*context, last)]
            old = source[src]
            word = destination.get(dst, mask if poison & 1 else 0)
            for src_col, dst_col in zip(columns[src_group*h:(src_group+1)*h], columns[dst_group*h:(dst_group+1)*h]):
                word = (word & ~(1 << dst_col)) | (((old >> src_col) & 1) << dst_col)
            destination[dst] = word
        else:
            primitive = LoweredPrimitive({"MAJ3": "TRA", "MAJ5": "5RA"}.get(opcode, opcode),
                                         tuple(operands), (), index, "GEMV physical replay")
            lowered = replace(template, primitives=(primitive,))
            for mat in range(first, last+1):
                key = (*context, mat)
                memory[key] = execute_physical(lowered, memory[key], width)
        if index in events:
            output, context, domain = events[index]
            rows = memory[(*context, domain["sink_mat"])]
            domain_sum = 0
            for lane in range(domain["residual_count"]):
                value = sum(((rows[row] >> column(lane)) & 1) << bit
                            for bit, row in enumerate(domain["result_rows"]))
                domain_sum = add(domain_sum, value)
            results[output] = add(results[output], domain_sum)
    return results
