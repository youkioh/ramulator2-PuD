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
    add_name, _ = PROFILES[profile]
    if add_name == "int8-add":
        return lambda a, b: (a+b) & 255, lambda a, b: (a*b) & 255
    format_ = {"fp8-e4m3-add": E4M3, "fp8-e5m2-add": E5M2}[add_name]

    @lru_cache(None)
    def add(a, b):
        fields = fp8_add_reference(a, b, format_)
        # Existing ADD exports low exponent bits outside its comparison domain.
        # This is raw graph equality, not a new IEEE FP8 numerical policy.
        return ((fields["result_sign"] << 7) |
                ((fields["exponent"] & format_.exponent_mask) << format_.fraction_bits) |
                fields["fraction"])
    return add, lambda a, b: scalar_fp8_mul_reference(a, b, format_)


def scalar_graph(profile, matrix, vector, *, target="DDR4"):
    """The .cu scalar MUL/ADD graph, independently over lists of valid terms."""
    add, mul = scalar_operations(profile)
    geometry = placement_profile(target)
    width, h = geometry["cells_per_mat_row"], geometry["hffs_per_mat"]
    domain_size = width * geometry["mats_per_chip"]

    def reduce_local(values):
        target = 1 << (len(values).bit_length()-1)
        if target != len(values):
            extra = len(values)-target
            values = [add(values[i], values[target+i]) for i in range(extra)] + values[extra:target]
        while len(values) > h:
            half = len(values)//2
            values = [add(values[i], values[half+i]) for i in range(half)]
        return values

    results = []
    for row in matrix:
        output_sum = 0
        for start in range(0, len(vector), domain_size):
            products = [mul(a, x) for a, x in zip(
                row[start:start+domain_size], vector[start:start+domain_size])]
            fragments = [products[offset:offset+width] for offset in range(0, len(products), width)]
            intra_first = profile.startswith("MIMDRAM-IntraMatFirst-")
            if intra_first:
                fragments = [reduce_local(local) for local in fragments]
            accumulator = fragments[0]
            for local in fragments[1:]:
                accumulator = [add(v, accumulator[i]) for i, v in enumerate(local)] + accumulator[len(local):]
            if not intra_first:
                accumulator = reduce_local(accumulator)
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
    geometry = layout_geometry(metadata)
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
                        rows.setdefault(first+bit, mask if (poison >> bit) & 1 else 0)
                for name, row_id in record["constant_rows"].items():
                    rows[row_id] = mask if name == program.one else 0
                valid = min(width, domain["elements"]-local_mat*width)
                for first, values in ((a_row, matrix[output]), (x_row, vector)):
                    for bit in range(bits):
                        word = rows.get(first+bit, mask if (poison >> bit) & 1 else 0)
                        for lane in range(valid):
                            pos = column(record.get("position_origin", 0)+lane)
                            word = (word & ~(1 << pos)) | (((values[start+local_mat*width+lane] >> bit) & 1) << pos)
                        rows[first+bit] = word
            events.setdefault(domain["completion_index"], []).append((output, context, domain))
            start += domain["elements"]

    protected = {}
    for record in metadata["outputs"]:
        for domain_index, domain in enumerate(record["domains"]):
            ids = list(record["constant_rows"].values())
            ids += [row+bit for row in record["input_rows"][domain_index] for bit in range(bits)]
            for mat in range(domain["mat_begin"], domain["mat_begin"]+domain["mat_count"]):
                key = (*record["context"], mat)
                for row in ids:
                    protected[key, row] = memory[key][row]

    template = replace(lower_to_physical(program, make_default_physical_layout(program)),
                       designated_inputs=(), designated_constants=(), result_bindings=(),
                       local_row_count=geometry["rows_per_bank"])
    add, _ = scalar_operations(metadata["macro_profile"])
    results = [0] * metadata["M"]
    for index, line in enumerate(trace, 1):
        opcode, *values = line.split()
        values = list(map(int, values))
        depth = len(metadata.get("bank_levels", ["Channel", "Rank", "BankGroup", "Bank"]))
        context = tuple(values[:depth])
        first, last, *operands = values[depth:]
        if opcode in ("LC-MOV", "GB-MOV"):
            src, src_group, dst, dst_group = operands
            pairs = ((mat, mat) for mat in range(first, last+1)) if opcode == "LC-MOV" else ((first, last),)
            for source_mat, destination_mat in pairs:
                source, destination = memory[(*context, source_mat)], memory[(*context, destination_mat)]
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
        for output, context, domain in events.get(index, []):
            rows = memory[(*context, domain["sink_mat"])]
            domain_sum = 0
            for lane in domain.get("residual_positions", range(domain["residual_count"])):
                value = sum(((rows[row] >> column(lane)) & 1) << bit
                            for bit, row in enumerate(domain["result_rows"]))
                domain_sum = add(domain_sum, value)
            results[output] = add(results[output], domain_sum)
    if any(memory[key].get(row) != value for (key, row), value in protected.items()):
        raise AssertionError("GEMV replay changed protected A/x/constant rows")
    return results


def layout_geometry(metadata):
    version = metadata.get("schema_version")
    if version not in (4, 5):
        raise ValueError("unsupported GEMV layout version")
    geometry = placement_profile(metadata["target"] if version == 5 else "DDR4")
    if metadata["placement_profile"] != geometry["name"]:
        raise ValueError("GEMV layout profile mismatch")
    if version == 5:
        if len(metadata["outputs"]) != metadata["M"]:
            raise ValueError("logical output count mismatch")
        for key in ("bank_levels", "bank_sizes"):
            if metadata[key] != geometry[key]:
                raise ValueError(f"GEMV layout {key} mismatch")
        h = geometry["hffs_per_mat"]
        groups = metadata["packed_output_groups"]
        members = []
        end = 0
        for chain_id, group in enumerate(groups):
            if group["chain_id"] != chain_id or group["first_request_index"] != end+1:
                raise ValueError("invalid physical CHAIN ownership")
            end = group["completion_index"]
            if not group["first_request_index"] <= group["initial_mul_final_request_index"] <= end:
                raise ValueError("invalid physical checkpoint")
            members.extend(group["output_ids"])
        if sorted(members) != list(range(metadata["M"])) or end != metadata["request_count"]:
            raise ValueError("packed output membership mismatch")
        for output_id, record in enumerate(metadata["outputs"]):
            if record["output_id"] != output_id or len(record["context"]) != len(geometry["bank_sizes"]):
                raise ValueError("invalid output identity")
            if any(type(v) is not int or not 0 <= v < bound for v, bound in zip(record["context"], geometry["bank_sizes"])):
                raise ValueError("output Bank identity out of bounds")
            origin = record["position_origin"]
            if (origin < 0 or origin % h or record["group_origin"] != origin//h or
                    origin+min(metadata["N"], geometry["cells_per_mat_row"]) > geometry["cells_per_mat_row"]):
                raise ValueError("invalid packed slice alignment")
            if type(record["chain_id"]) is not int or not 0 <= record["chain_id"] < len(groups):
                raise ValueError("invalid physical CHAIN identity")
            group = groups[record["chain_id"]]
            if (output_id not in group["output_ids"] or record["packed_output_group"] != group["chain_id"] or
                    record["context"] != group["context"] or record["first_request_index"] != group["first_request_index"] or
                    record["initial_mul_final_request_index"] != group["initial_mul_final_request_index"]):
                raise ValueError("output physical CHAIN mismatch")
            previous = record["first_request_index"]-1
            for domain in record["domains"]:
                if domain["residual_positions"] != list(range(origin, origin+h)):
                    raise ValueError("invalid output residual positions")
                if (domain["chain_id"] != record["chain_id"] or
                        not previous < domain["completion_index"] <= group["completion_index"] or
                        domain["checkpoint_request"] != domain["completion_index"]-record["first_request_index"]+1):
                    raise ValueError("output checkpoint ownership mismatch")
                previous = domain["completion_index"]
    return geometry


def read_gemv(path):
    """Read emitted v4/v5 artifacts and assert their shared trace association."""
    import json
    from pathlib import Path
    from .generator import trace_header
    path = Path(path)
    metadata = json.loads(path.with_suffix(".layout.json").read_text())
    layout_geometry(metadata)
    text = path.read_text()
    header = trace_header(metadata)
    if not text.startswith(header):
        raise ValueError("trace/layout header mismatch")
    records = metadata.get("packed_output_groups", metadata["outputs"])
    trace, selected, seen = [], None, set()
    for line in text[len(header):].splitlines():
        if line.startswith("CHAIN "):
            selected = int(line.split()[1])
            if selected < 0 or selected >= len(records) or selected in seen:
                raise ValueError("unknown physical CHAIN")
            seen.add(selected)
            if len(trace)+1 != records[selected]["first_request_index"]:
                raise ValueError("CHAIN boundary mismatch")
        else:
            if selected is None:
                raise ValueError("physical Request without CHAIN")
            record = records[selected]
            end = record["completion_index"] if metadata["schema_version"] == 5 else record["domains"][-1]["completion_index"]
            if len(trace) >= end:
                raise ValueError("physical Request exceeds CHAIN boundary")
            trace.append(line)
    if len(trace) != metadata["request_count"]:
        raise ValueError("trace/layout Request count mismatch")
    return metadata, trace
