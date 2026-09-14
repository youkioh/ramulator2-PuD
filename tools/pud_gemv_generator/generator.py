"""Static GEMV placement and physical trace composition; no arithmetic primitives here."""
from collections import Counter
import json
from pathlib import Path

from tools.pud_operation_generator import PhysicalRowLayout, lower_to_physical
from tools.pud_operation_generator.requirements import (
    BUILDERS, operation_requirements as micro_operation_requirements, write_requirements,
)

PROFILES = {
    "int8-gemv": ("int8-add", "int8-mul"),
    "fp8-e4m3-gemv": ("fp8-e4m3-add", "fp8-e4m3-mul"),
    "fp8-e5m2-gemv": ("fp8-e5m2-add", "fp8-e5m2-mul"),
}
OPCODES = {"TRA": "MAJ3", "5RA": "MAJ5"}


def placement_profile():
    # The C++ factory is the only source of geometry, group order and topology.
    from ramulator._ramulator import pud_placement_profile
    return pud_placement_profile()


def generate(profile, m, n):
    if profile not in PROFILES:
        raise ValueError("expected int8-gemv, fp8-e4m3-gemv or fp8-e5m2-gemv")
    geometry = placement_profile()
    width, h = geometry["cells_per_mat_row"], geometry["hffs_per_mat"]
    if type(m) is not int or m <= 0:
        raise ValueError("M must be a positive integer")
    if type(n) is not int or n <= 0 or n % h:
        raise ValueError(f"N must be positive and divisible by HFFS_PER_MAT ({h})")
    domain_mats = geometry["mats_per_chip"]
    domain_elements = width * domain_mats
    domain_count = (n + domain_elements - 1) // domain_elements
    mats = [0]
    while len(mats) < domain_mats:
        successor = geometry["gb_successor"][mats[-1]]
        if successor < 0:
            raise ValueError("placement profile lacks the required connected reduction domain")
        mats.append(successor)
    if mats != list(range(domain_mats)):
        raise ValueError("GEMV requires the current contiguous forward-domain placement")
    add_name, mul_name = PROFILES[profile]
    requirements = micro_operation_requirements()
    programs = {name: BUILDERS[name]() for name in PROFILES[profile]}
    op_rows = max(requirements[name]["additional_temporary_rows"] for name in programs)
    bits = requirements[mul_name]["output_rows"]
    if any(requirements[name]["input_rows"] != 2*bits or
           requirements[name]["output_rows"] != bits for name in programs):
        raise ValueError("GEMV requires matching fixed-width two-input ADD/MUL profiles")
    constant_names = sorted(set().union(*(p.constants for p in programs.values())))
    # One output owns a row band: distinct domain inputs and three reused
    # PuD macro-operation-level temporary-row workspaces, protected constants,
    # and PuD micro-operation-level temporary rows.
    footprint = 2*bits*domain_count + 3*bits + len(constant_names) + op_rows
    rows_per_subarray = geometry["rows_per_subarray"]
    outputs_per_subarray = rows_per_subarray // footprint
    if not outputs_per_subarray:
        raise ValueError("GEMV output layout exceeds local-row capacity")
    subarrays = geometry["rows_per_bank"] // rows_per_subarray
    contexts = geometry["bank_groups"] * geometry["banks_per_group"] * subarrays
    if m > contexts * outputs_per_subarray:
        raise ValueError("GEMV layout exceeds the one-rank placement capacity")
    trace, outputs, micro_operation_counts = [], [], Counter()

    def emit(opcode, context, first, last, *operands):
        trace.append(" ".join(map(str, (opcode, *context, first, last, *operands))))

    for output in range(m):
        context_index, slot = divmod(output, outputs_per_subarray)
        bank_index, subarray = divmod(context_index, subarrays)
        bg, bank = divmod(bank_index, geometry["banks_per_group"])
        context = [0, 0, bg, bank]
        base = slot * footprint
        external_base = subarray * rows_per_subarray
        primary = base + 2*bits*domain_count
        reduction, movement = primary + bits, primary + 2*bits
        constants = {name: primary + 3*bits + i for i, name in enumerate(constant_names)}
        temporary = tuple(range(primary + 3*bits + len(constants), base + footprint))
        record = {
            "context": context,
            "input_rows": [],
            "macro_operation_temporary_row_bases": {name: external_base + row for name, row in
                           (("primary", primary), ("reduction", reduction), ("movement", movement))},
            "constant_rows": {name: external_base + row for name, row in constants.items()},
            "micro_operation_temporary_rows": [external_base + row for row in temporary],
            "domains": [],
        }

        def arithmetic(name, a, b, dst, first, last):
            program = programs[name]
            count = requirements[name]["additional_temporary_rows"]
            layout = PhysicalRowLayout(
                rows_per_subarray,
                dict(zip(program.inputs, (*range(a, a+bits), *range(b, b+bits)))),
                {key: constants[key] for key in program.constants},
                dict(zip(program.outputs["R"], range(dst, dst+bits))),
                temporary_rows=temporary[:count],
            )
            lowered = lower_to_physical(program, layout)
            if lowered.additional_temporary_rows != count or len(lowered.primitives) != requirements[name]["primitive_count"]:
                raise AssertionError("operation requirements differ from physical instantiation")
            micro_operation_counts[name] += 1
            for primitive in lowered.primitives:
                emit(OPCODES.get(primitive.opcode, primitive.opcode), context, first, last,
                     *(external_base + row for row in primitive.physical_rows))

        def move(src, dst, src_mat, dst_mat, src_offset, dst_offset, count):
            if any(v % h for v in (src_offset, dst_offset, count)):
                raise ValueError("partial-group movement is unsupported")
            if not (0 <= src_offset <= src_offset+count <= width and
                    0 <= dst_offset <= dst_offset+count <= width):
                raise ValueError("movement exceeds mat-local element extent")
            opcode = "LC-MOV" if src_mat == dst_mat else "GB-MOV"
            if opcode == "GB-MOV" and geometry["gb_successor"][src_mat] != dst_mat:
                raise ValueError("movement is not a profile-supported directed neighbor")
            for bit in range(bits):
                for offset in range(0, count, h):
                    emit(opcode, context, src_mat, dst_mat,
                         external_base + src+bit, (src_offset+offset)//h,
                         external_base + dst+bit, (dst_offset+offset)//h)

        for domain in range(domain_count):
            elements = min(n - domain*domain_elements, domain_elements)
            k = (elements + width - 1) // width
            last_valid = elements - (k-1)*width
            a, x = base + domain*2*bits, base + domain*2*bits + bits
            record["input_rows"].append([external_base+a, external_base+x])
            arithmetic(mul_name, a, x, primary, mats[0], mats[k-1])
            current = primary
            for i in range(k-1):
                source, destination = mats[i], mats[i+1]
                valid = last_valid if i+1 == k-1 else width
                move(current, movement, source, destination, 0, 0, width)
                arithmetic(add_name, primary, movement, reduction, destination, destination)
                if valid < width:
                    move(movement, reduction, destination, destination, valid, valid, width-valid)
                current = reduction
            sink, valid = mats[k-1], last_valid if k == 1 else width
            alternate = reduction if current == primary else primary
            if valid & (valid-1):
                target = 1 << (valid.bit_length()-1)
                extra = valid-target
                move(current, movement, sink, sink, target, 0, extra)
                arithmetic(add_name, current, movement, alternate, sink, sink)
                if target > extra:
                    move(current, alternate, sink, sink, extra, extra, target-extra)
                current, alternate, valid = alternate, current, target
            while valid > h:
                half = valid//2
                move(current, movement, sink, sink, half, 0, half)
                arithmetic(add_name, current, movement, alternate, sink, sink)
                current, alternate, valid = alternate, current, half
            record["domains"].append({
                "elements": elements, "mat_count": k, "sink_mat": sink,
                "result_rows": list(range(external_base+current, external_base+current+bits)),
                "residual_count": valid, "completion_index": len(trace),
            })
        outputs.append(record)
    metadata = {
        "schema_version": 2, "macro_profile": profile, "M": m, "N": n,
        "placement_profile": geometry["name"], "ranks": 1,
        "micro_operation_requirements": {name: requirements[name] for name in programs},
        "micro_operation_counts": dict(micro_operation_counts),
        "micro_operation_temporary_rows_per_mat": op_rows,
        "rows_per_output_per_mat": footprint,
        "outputs": outputs,
        "request_counts": dict(Counter(line.split()[0] for line in trace)),
        "request_count": len(trace),
    }
    return metadata, trace


def write_gemv(profile, m, n, directory):
    metadata, trace = generate(profile, m, n)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    write_requirements(directory / "generated")
    (directory / f"{profile}.layout.json").write_text(
        json.dumps(metadata, indent=2)+"\n", encoding="utf-8"
    )
    header = f"PUD_TRACE\nPROFILE {metadata['placement_profile']}\nRANKS {metadata['ranks']}\n"
    path = directory / f"{profile}.trace"
    # Keep physical requests and their flattened completion indices unchanged.
    # Only the serialized stream adds dependency-chain selection directives.
    with path.open("w", encoding="utf-8") as stream:
        stream.write(header)
        start = 0
        for chain_id, output in enumerate(metadata["outputs"]):
            end = output["domains"][-1]["completion_index"]
            stream.write(f"CHAIN {chain_id}\n")
            stream.write("\n".join(trace[start:end])+"\n")
            start = end
    return metadata, path
