"""Generate and run one accepted GEMV baseline using production Ramulator APIs."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

import ramulator
from tools.pud_gemv_generator import write_gemv
from tools.pud_gemv_generator.generator import PROFILES, placement_profile
from tools.pud_gemv_generator.targets import TARGETS, target_config


def chain_latencies(layout, front):
    """Interpret opaque frontend checkpoints only at the GEMV experiment layer."""
    ids = front["latency_chain_ids"]
    expected = [output["chain_id"] for output in layout["outputs"]]
    timestamps = [front[field] for field in
                  ("first_submit_cycles", "checkpoint_complete_cycles", "final_complete_cycles")]
    if len(set(ids)) != len(ids) or set(ids) != set(expected) or any(len(v) != len(ids) for v in timestamps):
        raise RuntimeError("latency timestamps do not match generated output chains")
    rows = []
    for chain_id, first, mul, final in zip(ids, *timestamps):
        if not 0 <= first <= mul <= final:
            raise RuntimeError(f"missing or unordered latency timestamps for chain {chain_id}")
        rows.append(dict(chain_id=chain_id, first_submit_cycle=first,
                         mul_complete_cycle=mul, final_complete_cycle=final,
                         start_delay_cycles=first, mul_cycles=mul-first,
                         reduction_cycles=final-mul, chain_cycles=final-first))
    return rows


def aggregate_latencies(rows):
    """Percentiles linearly interpolate sorted samples at (count - 1) * p."""
    result = {}
    for field in ("mul_cycles", "reduction_cycles", "chain_cycles"):
        values = sorted(row[field] for row in rows)
        result.update({f"{field}_mean": mean(values), f"{field}_min": values[0],
                       f"{field}_max": values[-1]})
        for percentile in (50, 95, 99):
            position = (len(values) - 1) * percentile / 100
            lower = int(position)
            upper = min(lower + 1, len(values) - 1)
            result[f"{field}_p{percentile}"] = values[lower] + (values[upper] - values[lower]) * (position - lower)
    result["start_delay_cycles_mean"] = mean(row["start_delay_cycles"] for row in rows)
    return result


def run(profile, m, n, out, *, chain_csv=False, target="DDR4"):
    if target == "DDR4-packed":
        raise ValueError("packed DDR4 is a correctness-only mode; no performance baseline is authorized")
    geometry = placement_profile(target)
    selected = target_config(target)
    domain_elements = geometry["cells_per_mat_row"] * geometry["mats_per_chip"]
    if n > domain_elements:
        raise ValueError("phase latency experiment requires one domain per chain "
                         f"(N <= {domain_elements}); multi-domain chains interleave MUL and reduction")
    start = perf_counter()
    layout, trace = write_gemv(profile, m, n, out, target=target)
    trace_generation_seconds = perf_counter() - start
    command_path = trace.with_suffix(".commands.csv")
    # Infrastructure wall time, including simulator setup, run and finalization.
    # Neither metric is modeled GEMV latency.
    start = perf_counter()
    # Experiment configuration from docs/pud/ddr4-pud-user-guide.md,
    # "Canonical configuration"; presets own organization and timing values.
    dram = selected["dram"]
    controller = getattr(ramulator.controller, selected["controller"])(
        dram=dram,
        pud_buffer_size=32,
        pud_placement_profile=selected["profile"],
        scheduler=ramulator.scheduler.FRFCFS(),
        refresh_manager=getattr(ramulator.refresh_manager, selected["refresh"])(),
        row_policy=ramulator.row_policy.Open(),
        addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
        controller_plugins=[ramulator.controller_plugin.CmdTraceRecorder(path=str(command_path))],
    )
    memory_system = ramulator.memory_system.GenericDRAM(
        clock_ratio=1,
        controllers=[controller for _ in range(selected["channels"])],
        channel_mapper=ramulator.channel_mapper.CacheLineInterleave(),
    )
    physical_groups = layout.get("packed_output_groups", layout["outputs"])
    frontend = ramulator.frontend.PuDTrace(
        clock_ratio=1, path=str(trace),
        latency_chain_ids=[output["chain_id"] for output in physical_groups],
        latency_checkpoint_requests=[output["initial_mul_final_request_index"] - output["first_request_index"] + 1
                                     for output in physical_groups],
    )
    if target != "DDR4":
        trace.with_suffix(".config.json").write_text(json.dumps(dict(
            frontend=frontend.to_config(), memory_system=memory_system.to_config()), indent=2)+"\n")
    sim = ramulator.Simulation(frontend, memory_system)
    try:
        sim.run()
        stats = sim.stats
    finally:
        sim.finalize()
    simulation_wall_seconds = perf_counter() - start

    front = stats["frontend"]
    chains = chain_latencies(layout, front)
    chain_path = trace.with_suffix(".chains.csv") if chain_csv else None
    if chain_path is not None:
        with chain_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(chains[0]))
            writer.writeheader()
            writer.writerows(chains)
    raw_controllers = stats["memory_system"]["controller"]
    controllers = raw_controllers if isinstance(raw_controllers, list) else [raw_controllers]
    ctrl = controllers[0]
    # CmdTraceRecorder closes its per-channel file during finalize(). Count
    # actual issue records, independently of generated primitive requirements.
    command_trace = Path(str(command_path) + ".ch0")
    commands, per_channel = Counter(), []
    for channel, observed in enumerate(controllers):
        path = Path(str(command_path) + f".ch{channel}")
        with path.open(newline="", encoding="utf-8") as stream:
            channel_commands = Counter()
            for row in csv.DictReader(stream):
                if int(row["Channel"]) != channel:
                    raise RuntimeError("command observation lost global Channel identity")
                channel_commands[row["command"]] += 1
        commands.update(channel_commands)
        per_channel.append(dict(channel=channel, stats=observed, commands=dict(channel_commands),
                                command_trace_path=str(path.resolve())))
    if target == "DDR4" and sum(commands.values()) != front["physical_command_occurrences_completed"]:
        raise RuntimeError("recorded command count differs from completed command occurrences")
    counts = layout["request_counts"]
    if not (front["physical_requests_submitted"] == front["physical_requests_completed"]
            == layout["request_count"]):
        raise RuntimeError("completed Request count differs from generated layout")
    for opcode, expected in counts.items():
        name = opcode.lower().replace("-mov", "mov")
        if sum(c[f"num_pud_{name}_reqs_completed"] for c in controllers) != expected:
            raise RuntimeError(f"completed {opcode} count differs from generated layout")

    placement = []
    for index, output in enumerate(layout["outputs"]):
        placement.append({
            "output": index,
            "context": dict(zip(layout.get("bank_levels", ("channel", "rank", "bank_group", "bank")), output["context"])),
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
    result = {
        "profile": profile,
        "M": m,
        "N": n,
        "trace_generation_seconds": trace_generation_seconds,
        "simulation_wall_seconds": simulation_wall_seconds,
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
        **aggregate_latencies(chains),
        "chain_csv_path": str(chain_path.resolve()) if chain_path is not None else "",
    }
    if target != "DDR4":
        config = dram.to_config()
        tick_ps = config["timing"][dram.timing_params.index("tCK_ps")]
        boundary = max(front["final_complete_cycles"])
        if any(c["cycles"] != boundary for c in controllers):
            raise RuntimeError("controller clocks differ from the global PuD completion boundary")
        maintenance = {name: count for name, count in commands.items() if name.startswith(("REF", "RFM"))}
        if any(count for name, count in maintenance.items() if name.startswith("RFM")):
            raise RuntimeError("evaluation unexpectedly generated RFM")
        expected_occurrences = 0
        depth = len(layout["bank_levels"])
        for line in trace.read_text().splitlines()[4:]:
            fields = line.split()
            if fields[0] == "CHAIN":
                continue
            expected_occurrences += (len(fields)-(depth+3)+1 if fields[0] == "RowCopy"
                else {"MAJ3": 4, "MAJ5": 6, "NOT": 3, "NOT_COPY": 4, "LC-MOV": 6, "GB-MOV": 5}[fields[0]])
        if front["physical_command_occurrences_completed"] != expected_occurrences:
            raise RuntimeError("completed occurrence count differs from emitted primitive graph")
        result.update(standard=config["impl"], organization=selected["organization"],
            evaluation_unit=selected["evaluation_unit"], channel_count=selected["channels"],
            H=geometry["hffs_per_mat"], connected_path_mats=geometry["mats_per_chip"],
            tick_unit=selected["tick_unit"], tick_duration_ps=tick_ps,
            latency_metric="PuD in-memory phase latency", pud_in_memory_phase_ticks=boundary,
            pud_in_memory_phase_ns=boundary*tick_ps/1000,
            host_readout_and_folding_timed=False, residual_values_per_output=layout["residual_values_per_output"],
            host_add_calls=layout["host_add_calls"], logical_operation_counts=layout["logical_operation_counts"],
            logical_scalar_mul_calls=layout["logical_scalar_mul_calls"],
            logical_pud_scalar_add_calls=layout["logical_pud_scalar_add_calls"],
            logical_outputs=m, physical_requests_by_opcode=counts,
            physical_chains=len(physical_groups), active_controllers=len({g["context"][0] for g in physical_groups}),
            packing_factor=layout["packing_factor"], fused_range_widths=layout["fused_range_widths"],
            occupied_mat_rows=layout["occupied_mat_rows"], useful_position_utilization=layout["useful_position_utilization"],
            scheduler="FRFCFS", pud_queue_entries_per_controller=32, row_policy="Open",
            read_queue_entries_per_controller=32, write_queue_entries_per_controller=32,
            priority_queue_entries_per_controller=1568, frontend_clock_ratio=1, memory_clock_ratio=1,
            admission="one attempt per controller per frontend tick, rejection consumes budget",
            refresh_policy=selected["refresh"], refresh_scatter_interval=0,
            maintenance_commands=maintenance, maintenance_command_count=sum(maintenance.values()),
            non_pud_occurrence_command_count=sum(commands.values())-expected_occurrences,
            per_channel=per_channel, finite_control_engines_modeled=False, SALP=False,
            fidelity="Accepted project evaluation model; no vendor-calibrated or end-to-end latency claim",
            output_completion_observations=[dict(output_id=r["output_id"], chain_id=r["chain_id"],
                final_complete_cycle=next(c["final_complete_cycle"] for c in chains if c["chain_id"] == r["chain_id"]))
                for r in layout["outputs"]])
        trace.with_suffix(".stats.json").write_text(json.dumps(stats, indent=2)+"\n")
    return result


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
    parser.add_argument("--target", choices=TARGETS, default="DDR4")
    parser.add_argument("--out", type=Path, default=Path("build/pud-gemv"))
    parser.add_argument("--csv", type=Path, help="append one result row (structured fields are JSON)")
    parser.add_argument("--chain-csv", action="store_true",
                        help="write per-chain phase latencies to <out>/<profile>.chains.csv")
    args = parser.parse_args()
    try:
        result = run(args.profile, args.m, args.n, args.out, chain_csv=args.chain_csv, target=args.target)
        if args.csv is not None:
            append_csv(args.csv, result)
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
