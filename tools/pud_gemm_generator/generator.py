"""Compose the accepted Q[8,128] K[128,2048] workload from packed GEMV."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from tools.pud_gemv_generator.generator import (
    PROFILES, _fuse_group, generate as generate_gemv, placement_profile, trace_header,
)
from tools.pud_operation_generator.requirements import write_requirements

SHAPES = {"Q": [8, 128], "K": [128, 2048], "O": [8, 2048]}


def _relocate(line, context, row_offset=0, mat_offset=0):
    opcode, *fields = line.split()
    values = list(map(int, fields))
    values[:4] = context
    values[4] += mat_offset
    values[5] += mat_offset
    # Group selectors are positions, not rows. GB is not part of this graph.
    if opcode == "GB-MOV":
        raise ValueError("GEMM local graph must not contain GB movement")
    for index in (range(6, len(values), 2) if opcode == "LC-MOV" else range(6, len(values))):
        values[index] += row_offset
    return " ".join(map(str, (opcode, *values)))


def generate(profile):
    """Generate only the accepted shape; values are supplied separately to replay."""
    return _generate(profile)


def _generate(profile, *, banks=tuple(range(16)), local_outputs=64, fused=True):
    """Internal smaller fixtures retain real geometry; not a public shape policy.

    Fuse corresponding chip-local streams only after the GEMV composer has
    synchronized all packed slices. Replication does not extend any reduction.
    """
    geometry = placement_profile("DDR4-packed")
    if (geometry["bank_levels"] != ["Channel", "Rank", "BankGroup", "Bank"] or
            geometry["bank_sizes"] != [1, 1, 4, 4] or geometry["chips"] != 8 or
            geometry["mats_per_chip"] != 16 or geometry["cells_per_mat_row"] != 512 or
            geometry["hffs_per_mat"] != 4):
        raise ValueError("GEMM requires the accepted one-rank DDR4 geometry")
    if (not banks or len(set(banks)) != len(banks) or
            any(type(b) is not int or not 0 <= b < 16 for b in banks) or
            type(local_outputs) is not int or not 1 <= local_outputs <= 64):
        raise ValueError("invalid internal GEMM fixture")
    template, local_trace = generate_gemv(profile, local_outputs, 128, target="DDR4-packed")
    footprint = template["rows_per_output_per_mat"]
    if 2*footprint > geometry["rows_per_subarray"]:
        raise ValueError("GEMM bands exceed subarray capacity")

    # Compose once at base zero. Each member here is a whole chip-local packed
    # group with identical rows, LC pairs, destructive graph and frontier.
    rank_trace, members = [], []
    for chip in range(8):
        start = len(rank_trace)
        rank_trace.extend(_relocate(line, [0, 0, 0, 0], mat_offset=16*chip) for line in local_trace)
        members.append(dict(output_id=chip, chain_id=0, context=[0, 0, 0, 0],
            first_request_index=start+1,
            initial_mul_final_request_index=start+template["packed_output_groups"][0]["initial_mul_final_request_index"],
            domains=[dict(completion_index=len(rank_trace))]))
    if fused:
        _fuse_group(rank_trace, members, 4)

    trace, chains, groups, outputs = [], [], [], []
    for bank in banks:
        context = [0, 0, bank//4, bank%4]
        chain = dict(chain_id=bank, context=context, first_request_index=len(trace)+1, bands=[])
        for band in range(2):
            base = band*footprint
            start = len(trace)+1
            trace.extend(_relocate(line, context, base) for line in rank_trace)
            end = len(trace)
            group = dict(chain_id=bank, band=band, context=context,
                         first_request_index=start, completion_index=end, output_ids=[])
            chain["bands"].append(len(groups))
            groups.append(group)
            for chip in range(8):
                for local, source in enumerate(template["outputs"]):
                    key = bank*128 + band*64 + local
                    record = deepcopy(source)
                    record.pop("initial_mul_final_request_index")
                    record.pop("packed_output_group")
                    record.update(output_id=chip*2048+key, query=chip, key=key,
                        chip=chip, subarray=0, band=band, row_band_base=base,
                        chain_id=bank, context=context, first_request_index=start,
                        completion_index=end, checkpoint_request=end-chain["first_request_index"]+1)
                    record["input_rows"] = [[row+base for row in pair] for pair in record["input_rows"]]
                    for field in ("macro_operation_temporary_row_bases", "constant_rows"):
                        record[field] = {name: row+base for name, row in record[field].items()}
                    record["micro_operation_temporary_rows"] = [row+base for row in record["micro_operation_temporary_rows"]]
                    for domain in record["domains"]:
                        domain.update(mat_begin=domain["mat_begin"]+16*chip,
                                      sink_mat=domain["sink_mat"]+16*chip,
                                      chain_id=bank, completion_index=end,
                                      checkpoint_request=record["checkpoint_request"])
                        domain["result_rows"] = [row+base for row in domain["result_rows"]]
                    outputs.append(record)
                    group["output_ids"].append(record["output_id"])
            if band == 0:
                chain["checkpoint_request"] = end-chain["first_request_index"]+1
        chain["completion_index"] = len(trace)
        chains.append(chain)
    count = len(outputs)
    layout = dict(schema="pud-gemm", schema_version=1, shapes=deepcopy(SHAPES),
        macro_profile=profile, arithmetic_format=template["arithmetic_format"],
        target="DDR4-packed", placement_profile=geometry["name"],
        bank_levels=geometry["bank_levels"], bank_sizes=geometry["bank_sizes"],
        rows_per_band_per_mat=footprint,
        micro_operation_requirements=template["micro_operation_requirements"],
        logical_operation_counts={name: calls*count//local_outputs
                                  for name, calls in template["logical_operation_counts"].items()},
        logical_scalar_mul_calls=count*128, logical_pud_scalar_add_calls=count*124,
        host_add_calls=count*5, residual_values_per_output=4,
        chains=chains, band_groups=groups, outputs=outputs,
        request_counts=dict(Counter(line.split()[0] for line in trace)), request_count=len(trace))
    return layout, trace


def _write_artifacts(layout, trace, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"DDR4-packed-GEMM-{layout['macro_profile']}.trace"
    path.with_suffix(".layout.json").write_text(json.dumps(layout, indent=2)+"\n")
    with path.open("w") as stream:
        stream.write(trace_header(layout))
        for chain in layout["chains"]:
            stream.write(f"CHAIN {chain['chain_id']}\n")
            stream.write("\n".join(trace[chain["first_request_index"]-1:chain["completion_index"]])+"\n")
    return path


def write_gemm(profile, directory):
    layout, trace = generate(profile)
    path = _write_artifacts(layout, trace, directory)
    write_requirements(Path(directory) / "generated")
    return layout, path
