"""Run GEMM with band-completion timestamps, not independent output latencies.

output_completion_observations assigns each output its owning band's completion
cycle. Outputs in that band share one timestamp; no per-output timing is sampled.
These checkpoints also do not measure separate MUL/reduction phases.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from time import perf_counter

import ramulator
from tools.pud_gemv_generator.targets import target_config
from tools.pud_gemm_generator import read_gemm, write_gemm
from tools.pud_gemm_generator.generator import PROFILES


def _configuration(layout, path, command_path):
    selected = target_config("DDR4-packed")
    controller = ramulator.controller.GenericDDR(
        dram=selected["dram"], pud_buffer_size=32,
        pud_placement_profile=selected["profile"], scheduler=ramulator.scheduler.FRFCFS(),
        refresh_manager=ramulator.refresh_manager.NoRefresh(), row_policy=ramulator.row_policy.Open(),
        addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
        controller_plugins=[ramulator.controller_plugin.CmdTraceRecorder(path=str(command_path))])
    frontend = ramulator.frontend.PuDTrace(clock_ratio=1, path=str(path),
        latency_chain_ids=[c["chain_id"] for c in layout["chains"]],
        latency_checkpoint_requests=[c["checkpoint_request"] for c in layout["chains"]])
    memory = ramulator.memory_system.GenericDRAM(clock_ratio=1, controllers=[controller],
        channel_mapper=ramulator.channel_mapper.CacheLineInterleave())
    dram = selected["dram"]
    tick_ps = dram.to_config()["timing"][dram.timing_params.index("tCK_ps")]
    return frontend, memory, tick_ps


def _simulate(layout, path):
    """Internal entry also used by small, explicitly constructed test fixtures."""
    path = Path(path)
    command_path = path.with_suffix(".commands.csv")
    front_config, memory, tick_ps = _configuration(layout, path, command_path)
    path.with_suffix(".config.json").write_text(json.dumps(dict(
        frontend=front_config.to_config(), memory_system=memory.to_config()), indent=2)+"\n")
    start = perf_counter()
    sim = ramulator.Simulation(front_config, memory)
    try:
        sim.run()
        stats = sim.stats
    finally:
        sim.finalize()
    wall = perf_counter()-start
    front, controller = stats["frontend"], stats["memory_system"]["controller"]
    if not (front["physical_requests_submitted"] == front["physical_requests_completed"] == layout["request_count"]):
        raise RuntimeError("GEMM physical Request completion mismatch")
    for opcode, count in layout["request_counts"].items():
        name = opcode.lower().replace("-mov", "mov")
        if controller[f"num_pud_{name}_reqs_completed"] != count:
            raise RuntimeError(f"GEMM {opcode} completion mismatch")
    commands = Counter()
    with Path(str(command_path)+".ch0").open() as stream:
        for row in csv.DictReader(stream):
            if int(row["Channel"]) != 0:
                raise RuntimeError("GEMM command escaped its Channel")
            commands[row["command"]] += 1
    if sum(commands.values()) != front["physical_command_occurrences_completed"]:
        raise RuntimeError("GEMM command occurrence accounting mismatch")
    expected_occurrences = 0
    for line in path.read_text().splitlines()[4:]:
        fields = line.split()
        if fields[0] != "CHAIN":
            expected_occurrences += (len(fields)-6 if fields[0] == "RowCopy" else
                {"MAJ3": 4, "MAJ5": 6, "NOT": 3, "NOT_COPY": 4, "LC-MOV": 6}[fields[0]])
    if expected_occurrences != front["physical_command_occurrences_completed"]:
        raise RuntimeError("GEMM completion differs from physical occurrence graph")
    if any(v for cmd, v in commands.items() if cmd.startswith(("REF", "RFM"))):
        raise RuntimeError("GEMM NoRefresh run issued maintenance")
    ids = [c["chain_id"] for c in layout["chains"]]
    if front["latency_chain_ids"] != ids:
        raise RuntimeError("GEMM checkpoint CHAIN identity mismatch")
    chains = []
    for index, chain_id in enumerate(ids):
        first = front["first_submit_cycles"][index]
        band0 = front["checkpoint_complete_cycles"][index]
        band1 = front["final_complete_cycles"][index]
        if not 0 <= first < band0 < band1:
            raise RuntimeError("invalid GEMM band-completion timestamps")
        chains.append(dict(chain_id=chain_id, first_submit_cycle=first,
                           band0_complete_cycle=band0, band1_complete_cycle=band1))
    boundary = max(c["band1_complete_cycle"] for c in chains)
    if controller["cycles"] != boundary:
        raise RuntimeError("GEMM elapsed time excludes final recovery")
    by_chain = {c["chain_id"]: c for c in chains}
    result = dict(profile=layout["macro_profile"], shapes=layout["shapes"],
        physical_chains=len(chains), logical_outputs=len(layout["outputs"]),
        logical_operation_counts=layout["logical_operation_counts"],
        logical_scalar_mul_calls=layout["logical_scalar_mul_calls"],
        logical_pud_scalar_add_calls=layout["logical_pud_scalar_add_calls"],
        host_add_calls=layout["host_add_calls"], residual_values_per_output=4,
        physical_requests=front["physical_requests_completed"],
        physical_requests_by_opcode=layout["request_counts"],
        issued_commands=dict(commands), issued_command_occurrences=sum(commands.values()),
        physical_command_occurrences_completed=front["physical_command_occurrences_completed"],
        peak_inflight_requests=front["physical_requests_peak_inflight"],
        pud_in_memory_phase_ticks=boundary, tick_duration_ps=tick_ps,
        pud_in_memory_phase_ns=boundary*tick_ps/1000, simulation_wall_seconds=wall,
        refresh_policy="NoRefresh", inputs_preplaced_and_replicated=True,
        loading_readout_host_folding_timed=False, terminal_recovery_included=True,
        chains=chains, output_completion_observations=[dict(
            output_id=r["output_id"], query=r["query"], key=r["key"], chain_id=r["chain_id"], band=r["band"],
            complete_cycle=by_chain[r["chain_id"]][f"band{r['band']}_complete_cycle"])
            for r in layout["outputs"]])
    path.with_suffix(".stats.json").write_text(json.dumps(stats, indent=2)+"\n")
    path.with_suffix(".result.json").write_text(json.dumps(result, indent=2)+"\n")
    return result


def run(profile, out):
    start = perf_counter()
    _, path = write_gemm(profile, out)
    layout, _ = read_gemm(path)
    generation = perf_counter()-start
    result = _simulate(layout, path)
    result["trace_generation_and_validation_seconds"] = generation
    path.with_suffix(".result.json").write_text(json.dumps(result, indent=2)+"\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.profile, args.out)
    print(f"{result['physical_chains']} CHAINs: {result['pud_in_memory_phase_ns']} ns PuD time")
