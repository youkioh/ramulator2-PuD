"""Static GEMV placement and physical trace composition; no arithmetic primitives here."""
from collections import Counter
import json
from pathlib import Path

from tools.pud_operation_generator import PhysicalRowLayout, lower_to_physical
from tools.pud_operation_generator.requirements import (
    BUILDERS, operation_requirements as micro_operation_requirements, write_requirements,
)

BASELINES = ("MIMDRAM-InterMatFirst", "MIMDRAM-IntraMatFirst")
FORMATS = ("int8", "fp8-e4m3", "fp8-e5m2")
PROFILES = {f"{baseline}-{format_}": (f"{format_}-add", f"{format_}-mul")
            for baseline in BASELINES for format_ in FORMATS}
OPCODES = {"TRA": "MAJ3", "5RA": "MAJ5"}


def placement_profile():
    # The C++ factory is the only source of geometry, group order and topology.
    from ramulator._ramulator import pud_placement_profile
    return pud_placement_profile()


def _output_placement(geometry, k, footprint, output):
    """Static bank/group/range/chip/subarray/band order; subarrays add no SALP."""
    rows = geometry["rows_per_subarray"]
    per_chip = geometry["mats_per_chip"]
    if not 1 <= k <= per_chip or output < 0 or footprint <= 0:
        raise ValueError("invalid GEMV placement dimensions")
    bands = rows // footprint
    if not bands:
        raise ValueError("GEMV output layout exceeds local-row capacity")
    remaining, bank = divmod(output, geometry["banks_per_group"])
    remaining, bg = divmod(remaining, geometry["bank_groups"])
    remaining, slot = divmod(remaining, per_chip // k)
    remaining, chip = divmod(remaining, geometry["chips"])
    band, subarray = divmod(remaining, geometry["rows_per_bank"] // rows)
    if band >= bands:
        raise ValueError("GEMV layout exceeds the one-rank placement capacity")
    first = chip * per_chip + slot * k
    mats = tuple(range(first, first + k))
    if any(geometry["gb_successor"][a] != b for a, b in zip(mats, mats[1:])):
        raise ValueError("GEMV requires a profile-supported contiguous forward range")
    return [0, 0, bg, bank], subarray, band * footprint, mats


def generate(profile, m, n):
    if profile not in PROFILES:
        raise ValueError("expected an explicit baseline/profile: " + ", ".join(PROFILES))
    baseline, format_ = profile.split("-", 2)[1:]
    geometry = placement_profile()
    width, h = geometry["cells_per_mat_row"], geometry["hffs_per_mat"]
    if type(m) is not int or m <= 0:
        raise ValueError("M must be a positive integer")
    if type(n) is not int or n <= 0 or n % h:
        raise ValueError(f"N must be positive and divisible by HFFS_PER_MAT ({h})")
    domain_mats = geometry["mats_per_chip"]
    domain_elements = width * domain_mats
    domain_count = (n + domain_elements - 1) // domain_elements
    output_mats = (min(n, domain_elements) + width - 1) // width
    add_name, mul_name = PROFILES[profile]
    requirements = micro_operation_requirements()
    programs = {name: BUILDERS[name]() for name in PROFILES[profile]}
    op_rows = max(requirements[name]["additional_temporary_rows"] for name in programs)
    bits = requirements[mul_name]["output_rows"]
    if any(requirements[name]["input_rows"] != 2*bits or
           requirements[name]["output_rows"] != bits for name in programs):
        raise ValueError("GEMV requires matching fixed-width two-input ADD/MUL profiles")
    constant_names = sorted(set().union(*(p.constants for p in programs.values())))
    # One output owns a row band in its reserved mat range: domain inputs and three reused
    # PuD macro-operation-level temporary-row workspaces, protected constants,
    # and PuD micro-operation-level temporary rows.
    footprint = 2*bits*domain_count + 3*bits + len(constant_names) + op_rows
    rows_per_subarray = geometry["rows_per_subarray"]
    # Reject excessive M before lowering any arithmetic or materializing outputs.
    _output_placement(geometry, output_mats, footprint, m - 1)
    trace, outputs, micro_operation_counts = [], [], Counter()

    def emit(opcode, context, first, last, *operands):
        trace.append(" ".join(map(str, (opcode, *context, first, last, *operands))))

    for output in range(m):
        context, subarray, base, mats = _output_placement(
            geometry, output_mats, footprint, output)
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

        def move(src, dst, src_mat, dst_mat, src_offset, dst_offset, count, *, local_last=None):
            if any(v % h for v in (src_offset, dst_offset, count)):
                raise ValueError("partial-group movement is unsupported")
            if not (0 <= src_offset <= src_offset+count <= width and
                    0 <= dst_offset <= dst_offset+count <= width):
                raise ValueError("movement exceeds mat-local element extent")
            opcode = "LC-MOV" if src_mat == dst_mat else "GB-MOV"
            if local_last is not None:
                if opcode != "LC-MOV" or not mats[0] <= src_mat <= local_last <= mats[-1]:
                    raise ValueError("local movement range must stay within this output")
            if opcode == "GB-MOV" and geometry["gb_successor"][src_mat] != dst_mat:
                raise ValueError("movement is not a profile-supported directed neighbor")
            for bit in range(bits):
                for offset in range(0, count, h):
                    emit(opcode, context, src_mat, dst_mat if local_last is None else local_last,
                         external_base + src+bit, (src_offset+offset)//h,
                         external_base + dst+bit, (dst_offset+offset)//h)

        def reduce_local(current, valid, first, last):
            # Identical mat-local stages share one invocation only within this
            # output. A partial final mat is reduced separately, without padding.
            alternate = reduction if current == primary else primary
            if valid & (valid-1):
                target = 1 << (valid.bit_length()-1)
                extra = valid-target
                move(current, movement, first, first, target, 0, extra, local_last=last)
                arithmetic(add_name, current, movement, alternate, first, last)
                if target > extra:
                    move(current, alternate, first, first, extra, extra, target-extra, local_last=last)
                current, alternate, valid = alternate, current, target
            while valid > h:
                half = valid//2
                move(current, movement, first, first, half, 0, half, local_last=last)
                arithmetic(add_name, current, movement, alternate, first, last)
                current, alternate, valid = alternate, current, half
            return current, valid

        for domain in range(domain_count):
            elements = min(n - domain*domain_elements, domain_elements)
            k = (elements + width - 1) // width
            last_valid = elements - (k-1)*width
            a, x = base + domain*2*bits, base + domain*2*bits + bits
            record["input_rows"].append([external_base+a, external_base+x])
            arithmetic(mul_name, a, x, primary, mats[0], mats[k-1])
            sink = mats[k-1]
            if baseline == "InterMatFirst":
                current = primary
                for i in range(k-1):
                    source, destination = mats[i], mats[i+1]
                    valid = last_valid if i+1 == k-1 else width
                    move(current, movement, source, destination, 0, 0, width)
                    arithmetic(add_name, primary, movement, reduction, destination, destination)
                    if valid < width:
                        move(movement, reduction, destination, destination, valid, valid, width-valid)
                    current = reduction
                current, valid = reduce_local(current, last_valid if k == 1 else width, sink, sink)
            else:
                full_mats = elements // width
                local_rows = []
                if full_mats:
                    current, valid = reduce_local(primary, width, mats[0], mats[full_mats-1])
                    local_rows = [current] * full_mats
                if last_valid < width:
                    current, valid = reduce_local(primary, last_valid, sink, sink)
                    local_rows.append(current)
                current = local_rows[0]
                for i in range(1, k):
                    destination = mats[i]
                    move(current, movement, mats[i-1], destination, 0, 0, valid)
                    local = local_rows[i]
                    alternate = reduction if local == primary else primary
                    arithmetic(add_name, local, movement, alternate, destination, destination)
                    current = alternate
            record["domains"].append({
                "elements": elements, "mat_begin": mats[0], "mat_count": k, "sink_mat": sink,
                "result_rows": list(range(external_base+current, external_base+current+bits)),
                "residual_count": valid, "completion_index": len(trace),
            })
        outputs.append(record)
    metadata = {
        "schema_version": 4, "macro_profile": profile, "M": m, "N": n,
        "baseline": "MIMDRAM-" + baseline, "arithmetic_format": format_,
        "output_placement": "BLP-first",
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
