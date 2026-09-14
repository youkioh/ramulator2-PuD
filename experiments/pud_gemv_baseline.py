"""Generate and run one accepted GEMV baseline using production Ramulator APIs."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path

import ramulator
from tools.pud_gemv_generator import write_gemv
from tools.pud_gemv_generator.generator import PROFILES


def run(profile, m, n, out):
    layout, trace = write_gemv(profile, m, n, out)
    command_path = trace.with_suffix(".commands.csv")
    # Experiment configuration from docs/pud/ddr4-pud-user-guide.md,
    # "Canonical configuration"; presets own organization and timing values.
    dram = ramulator.dram.DDR4_PuD_Movement(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
        hffs_per_mat=4,
    )
    controller = ramulator.controller.GenericDDR(
        dram=dram,
        pud_buffer_size=32,
        pud_placement_profile="MIMDRAM_DDR4_8Gb_x8_v1",
        pud_compute_engines=8,
        scheduler=ramulator.scheduler.FRFCFS(),
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
        row_policy=ramulator.row_policy.Open(),
        addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
        controller_plugins=[ramulator.controller_plugin.CmdTraceRecorder(path=str(command_path))],
    )
    memory_system = ramulator.memory_system.GenericDRAM(
        clock_ratio=1,
        controllers=[controller],
        channel_mapper=ramulator.channel_mapper.CacheLineInterleave(),
    )
    frontend = ramulator.frontend.PuDTrace(clock_ratio=1, path=str(trace))
    sim = ramulator.Simulation(frontend, memory_system)
    try:
        sim.run()
        stats = sim.stats
    finally:
        sim.finalize()

    front = stats["frontend"]
    ctrl = stats["memory_system"]["controller"]
    # CmdTraceRecorder closes its per-channel file during finalize(). Count
    # actual issue records, independently of generated primitive requirements.
    command_trace = Path(str(command_path) + ".ch0")
    with command_trace.open(newline="", encoding="utf-8") as stream:
        commands = Counter(row["command"] for row in csv.DictReader(stream))
    if sum(commands.values()) != front["physical_command_occurrences_completed"]:
        raise RuntimeError("recorded command count differs from completed command occurrences")
    counts = layout["request_counts"]
    if not (front["physical_requests_submitted"] == front["physical_requests_completed"]
            == layout["request_count"]):
        raise RuntimeError("completed Request count differs from generated layout")
    for opcode, expected in counts.items():
        name = opcode.lower().replace("-mov", "mov")
        if ctrl[f"num_pud_{name}_reqs_completed"] != expected:
            raise RuntimeError(f"completed {opcode} count differs from generated layout")

    placement = []
    for index, output in enumerate(layout["outputs"]):
        placement.append({
            "output": index,
            "context": dict(zip(("channel", "rank", "bank_group", "bank"), output["context"])),
            "mat_begin": output["domains"][0]["mat_begin"],
            "mat_end": max(domain["sink_mat"] for domain in output["domains"]),
            # Full bank row identity distinguishes subarray/row-band fallback.
            "first_input_row": output["input_rows"][0][0],
        })
    resources = {}
    for operation, name in zip(("add", "mul"), PROFILES[profile]):
        requirement = layout["micro_operation_requirements"][name]
        # These requirements describe one PuD micro-operation invocation.
        for field, value in requirement.items():
            resources[f"{operation}_{field}"] = value
        resources[f"{operation}_micro_operation_invocation_count"] = layout["micro_operation_counts"].get(name, 0)

    # All three PuD macro-operation workspaces hold arithmetic-width values.
    # Width and workspace roles come from the generated metadata, not constants.
    width = resources["mul_output_rows"]
    macro_rows = {role: width for role in layout["outputs"][0]["macro_operation_temporary_row_bases"]}
    peak_micro_rows = layout["micro_operation_temporary_rows_per_mat"]
    resources["micro_operation_temporary_rows_per_mat"] = peak_micro_rows
    resources.update({f"macro_operation_{role}_temporary_rows_per_output_per_mat": count
                      for role, count in macro_rows.items()})
    resources["macro_operation_temporary_rows_per_output_per_mat"] = sum(macro_rows.values())
    resources["total_temporary_rows_per_output_per_mat"] = sum(macro_rows.values()) + peak_micro_rows
    resources["rows_per_output_per_mat"] = layout["rows_per_output_per_mat"]

    request_names = ("RowCopy", "MAJ3", "MAJ5", "NOT", "NOT_COPY", "LC-MOV", "GB-MOV")
    # Include zero counts for the baseline commands and retain any other actual
    # emitted command identities rather than dropping them from the breakdown.
    command_names = ("ACT_PUD_OC", "ACT_PUD", "ACT_PUD_S", "ACT_PUD_S_OC", "N",
                     "PREpb", "ACT_MOV", "RD_MOV", "WR_MOV")
    command_names = dict.fromkeys((*command_names, *sorted(commands)))
    return {
        "profile": profile,
        "M": m,
        "N": n,
        "baseline": layout["baseline"],
        "arithmetic_format": layout["arithmetic_format"],
        "placement_profile": layout["placement_profile"],
        "output_placement_policy": layout["output_placement"],
        "output_placement": placement,
        "layout_json_path": str(trace.with_suffix(".layout.json").resolve()),
        "command_trace_path": str(command_trace.resolve()),
        **resources,
        "compute_primitive_requests": sum(count for opcode, count in counts.items()
                                          if opcode not in ("LC-MOV", "GB-MOV")),
        **{f"{opcode.lower().replace('-', '_')}_requests": counts.get(opcode, 0)
           for opcode in request_names},
        "physical_requests": front["physical_requests_completed"],
        **{f"issued_{command}_commands": commands[command] for command in command_names},
        "issued_dram_commands": sum(commands.values()),
        "physical_command_occurrences_completed": front["physical_command_occurrences_completed"],
        "prada_notation": {"A*": "ACT_PUD_OC", "A": "ACT_PUD", "A_S": "ACT_PUD_S",
                           "A*_S": "ACT_PUD_S_OC", "P": "PREpb", "N": "N"},
        "peak_inflight_requests": front["physical_requests_peak_inflight"],
        "controller_cycles": ctrl["cycles"],
    }


def append_csv(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {key: json.dumps(value) if isinstance(value, (dict, list)) else value
           for key, value in result.items()}
    with path.open("a+", newline="", encoding="utf-8") as stream:
        stream.seek(0)
        header = next(csv.reader(stream), None)
        if header is not None and header != list(row):
            raise ValueError("CSV header differs from current result fields; use a new CSV path")
        stream.seek(0, 2)
        writer = csv.DictWriter(stream, fieldnames=list(row))
        if header is None:
            writer.writeheader()
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, required=True)
    parser.add_argument("--m", type=int, required=True)
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--out", type=Path, default=Path("build/pud-gemv"))
    parser.add_argument("--csv", type=Path, help="append one result row (structured fields are JSON)")
    args = parser.parse_args()
    try:
        result = run(args.profile, args.m, args.n, args.out)
        if args.csv is not None:
            append_csv(args.csv, result)
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
