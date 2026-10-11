"""GEMM schema ownership, shared physical replay and independent indexed oracle."""
from collections import Counter
import json
from pathlib import Path

from tools.pud_gemv_generator.generator import PROFILES, placement_profile, trace_header
from tools.pud_gemv_generator.validation import _execute_trace, scalar_operations
from tools.pud_operation_generator.requirements import BUILDERS, operation_requirements
from .generator import SHAPES


def validate_layout(layout, *, _partial=False):
    if (layout.get("schema") != "pud-gemm" or layout.get("schema_version") != 1 or
            layout.get("shapes") != SHAPES or layout.get("target") != "DDR4-packed" or
            layout.get("macro_profile") not in PROFILES):
        raise ValueError("unsupported GEMM layout contract")
    geometry = placement_profile("DDR4-packed")
    for field, expected in (("placement_profile", geometry["name"]),
                            ("bank_levels", geometry["bank_levels"]), ("bank_sizes", geometry["bank_sizes"])):
        if layout[field] != expected:
            raise ValueError(f"GEMM {field} mismatch")
    requirements = operation_requirements()
    names = PROFILES[layout["macro_profile"]]
    if layout["arithmetic_format"] != layout["macro_profile"].split("-", 2)[2]:
        raise ValueError("GEMM arithmetic format mismatch")
    if layout["micro_operation_requirements"] != {name: requirements[name] for name in names}:
        raise ValueError("GEMM arithmetic requirements mismatch")
    constants = sorted(set().union(*(BUILDERS[name]().constants for name in names)))
    temps = max(requirements[name]["additional_temporary_rows"] for name in names)
    footprint = 40+len(constants)+temps
    if layout["rows_per_band_per_mat"] != footprint or 2*footprint > geometry["rows_per_subarray"]:
        raise ValueError("invalid GEMM row capacity")
    chains, groups = layout["chains"], layout["band_groups"]
    ids = [c["chain_id"] for c in chains]
    if (not ids or len(set(ids)) != len(ids) or
            any(type(i) is not int or not 0 <= i < 16 for i in ids) or
            (not _partial and ids != list(range(16))) or len(groups) != 2*len(chains)):
        raise ValueError("GEMM requires one CHAIN per Bank")
    ownership, end = {}, 0
    for index, chain in enumerate(chains):
        bank = chain["chain_id"]
        context = [0, 0, bank//4, bank%4]
        if chain["context"] != context or chain["first_request_index"] != end+1 or chain["bands"] != [2*index, 2*index+1]:
            raise ValueError("invalid Bank CHAIN ownership")
        for band in range(2):
            group = groups[2*index+band]
            if (group["chain_id"] != bank or group["band"] != band or group["context"] != context or
                    group["first_request_index"] != end+1 or group["completion_index"] < end+1):
                raise ValueError("invalid band ordering")
            end = group["completion_index"]
            for output_id in group["output_ids"]:
                if output_id in ownership:
                    raise ValueError("duplicate GEMM output ownership")
                ownership[output_id] = (chain, group)
            if band == 0 and chain["checkpoint_request"] != end-chain["first_request_index"]+1:
                raise ValueError("GEMM checkpoint must mean band-0 completion")
        if chain["completion_index"] != end:
            raise ValueError("GEMM final completion must mean band-1 completion")
    if end != layout["request_count"] or len(ownership) != len(layout["outputs"]):
        raise ValueError("GEMM Request/output coverage mismatch")
    seen = set()
    for record in layout["outputs"]:
        h, j = record["query"], record["key"]
        output_id = record["output_id"]
        if (type(h) is not int or type(j) is not int or not 0 <= h < 8 or not 0 <= j < 2048 or
                output_id != h*2048+j or output_id in seen or output_id not in ownership):
            raise ValueError("invalid GEMM query/key identity")
        seen.add(output_id)
        chain, group = ownership[output_id]
        bank, band, mat, origin = j//128, (j%128)//64, h*16+(j%64)//4, 128*(j%4)
        base = band*footprint
        if (record["chip"] != h or record["subarray"] != 0 or record["band"] != band or
                record["row_band_base"] != base or record["chain_id"] != bank or
                chain["chain_id"] != bank or group["band"] != band or
                record["context"] != chain["context"] or record["position_origin"] != origin or
                record["group_origin"] != origin//4 or record["first_request_index"] != group["first_request_index"] or
                record["completion_index"] != group["completion_index"] or
                record["checkpoint_request"] != group["completion_index"]-chain["first_request_index"]+1):
            raise ValueError("GEMM placement/checkpoint ownership mismatch")
        if (record["input_rows"] != [[base, base+8]] or
                record["macro_operation_temporary_row_bases"] != dict(primary=base+16, reduction=base+24, movement=base+32) or
                record["constant_rows"] != {name: base+40+i for i, name in enumerate(constants)} or
                record["micro_operation_temporary_rows"] != list(range(base+40+len(constants), base+footprint))):
            raise ValueError("GEMM row roles mismatch")
        expected = dict(elements=128, mat_begin=mat, mat_count=1, sink_mat=mat,
            result_rows=list(range(base+24, base+32)), residual_count=4,
            completion_index=group["completion_index"], domain=0, term_begin=0, term_end=128,
            residual_positions=list(range(origin, origin+4)), chain_id=bank,
            checkpoint_request=record["checkpoint_request"])
        if record["domains"] != [expected]:
            raise ValueError("GEMM residual ownership mismatch")
    if not _partial and seen != set(range(8*2048)):
        raise ValueError("GEMM must cover all 8 x 2048 outputs")
    if not _partial:
        count = len(seen)
        for field, expected in (("logical_scalar_mul_calls", count*128),
                                ("logical_pud_scalar_add_calls", count*124),
                                ("host_add_calls", count*5), ("residual_values_per_output", 4),
                                ("logical_operation_counts", {names[0]: count*5, names[1]: count})):
            if layout[field] != expected:
                raise ValueError(f"GEMM {field} mismatch")
    return geometry


def validate_trace(layout, trace, *, _partial=False):
    geometry = validate_layout(layout, _partial=_partial)
    if len(trace) != layout["request_count"] or Counter(line.split()[0] for line in trace) != layout["request_counts"]:
        raise ValueError("GEMM physical Request count mismatch")
    footprint = layout["rows_per_band_per_mat"]
    for group in layout["band_groups"]:
        base = group["band"]*footprint
        for line in trace[group["first_request_index"]-1:group["completion_index"]]:
            opcode, *fields = line.split()
            values = list(map(int, fields))
            counts = {"MAJ3": 3, "MAJ5": 5, "NOT": 1, "LC-MOV": 4}
            operands = values[6:]
            if (opcode not in (*counts, "RowCopy", "NOT_COPY") or
                    (opcode in counts and len(operands) != counts[opcode]) or
                    (opcode in ("RowCopy", "NOT_COPY") and len(operands) < 2) or
                    values[:4] != group["context"] or len(values) < 7 or
                    not 0 <= values[4] <= values[5] < 128 or
                    (not _partial and values[4:6] != [0, 127])):
                raise ValueError("illegal GEMM Request scope")
            rows = operands[::2] if opcode == "LC-MOV" else operands
            if any(not base <= row < base+footprint for row in rows):
                raise ValueError("Request crosses GEMM row band")
            if opcode == "LC-MOV" and any(not 0 <= g < 128 for g in operands[1::2]):
                raise ValueError("illegal GEMM LC Group")
    return geometry


def read_gemm(path):
    path = Path(path)
    layout = json.loads(path.with_suffix(".layout.json").read_text())
    validate_layout(layout)
    header = trace_header(layout)
    text = path.read_text()
    if not text.startswith(header):
        raise ValueError("GEMM trace/layout header mismatch")
    lines = iter(text[len(header):].splitlines())
    trace = []
    for chain in layout["chains"]:
        if next(lines, None) != f"CHAIN {chain['chain_id']}":
            raise ValueError("GEMM trace/CHAIN boundary mismatch")
        for _ in range(chain["completion_index"]-chain["first_request_index"]+1):
            line = next(lines, None)
            if line is None or line.startswith("CHAIN"):
                raise ValueError("incomplete GEMM CHAIN")
            trace.append(line)
    if next(lines, None) is not None:
        raise ValueError("extra GEMM trace data")
    validate_trace(layout, trace)
    return layout, trace


def _check_inputs(q, k):
    if len(q) != 8 or any(len(row) != 128 for row in q) or len(k) != 128 or any(len(row) != 2048 for row in k):
        raise ValueError("expected Q[8,128] and shared K[128,2048]")
    if any(type(v) is not int or not 0 <= v < 256 for rows in (q, k) for row in rows for v in row):
        raise ValueError("GEMM inputs must contain raw 8-bit values")


def execute_trace(layout, trace, q, k, poison=0xA5):
    """Return scalar O after physical residual replay and untimed host folding."""
    validate_trace(layout, trace)
    result = _replay(layout, trace, q, k, poison)
    return [[result[h, j] for j in range(2048)] for h in range(8)]


def _replay(layout, trace, q, k, poison=0xA5):
    _check_inputs(q, k)
    geometry = placement_profile("DDR4-packed")
    outputs = layout["outputs"]
    matrix = [[k[r][record["key"]] for r in range(128)] for record in outputs]
    internal = dict(layout, M=len(outputs), N=128)
    values = _execute_trace(internal, trace, matrix, lambda i: q[outputs[i]["query"]],
                            geometry, poison, retain_residuals=True)
    return {(record["query"], record["key"]): value for record, value in zip(outputs, values)}


def scalar_graph(profile, q, k):
    """Independent indexed oracle; no generated trace/layout determines its graph."""
    _check_inputs(q, k)
    return [[_scalar_output(profile, q[h], k, j) for j in range(2048)] for h in range(8)]


def _scalar_output(profile, query, k, j):
    add, mul = scalar_operations(profile)
    values = [mul(k[r][j], query[r]) for r in range(128)]
    for half in (64, 32, 16, 8, 4):
        values = [add(values[r], values[r+half]) for r in range(half)]
    residual_sum = 0
    for value in values:
        residual_sum = add(residual_sum, value)
    return add(0, residual_sum)
