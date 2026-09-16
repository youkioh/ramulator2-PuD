"""Thin frontend integration over the existing unified-substrate test setup."""
import csv
import json
from collections import Counter
from pathlib import Path
import pytest
import ramulator
from ramulator._ramulator_test import _PuDTraceUnderTest
from ramulator.dram.spec import REQUEST_TYPE_IDS
from tools.pud_gemv_generator.generator import PROFILES, _output_placement, placement_profile, write_gemv
from tests.unit_tests.test_pud_request_locations import controller
from tests.unit_tests.test_pud_location import resolver


def report_baseline(metadata, stats):
    counts = metadata["request_counts"]
    result = dict(profile=metadata["macro_profile"], M=metadata["M"], N=metadata["N"],
                  placement=[dict(context=r["context"], first=d["mat_begin"],
                                  last=d["sink_mat"]) for r in metadata["outputs"] for d in r["domains"]],
                  compute=sum(v for k, v in counts.items() if k not in ("LC-MOV", "GB-MOV")),
                  LC=counts.get("LC-MOV", 0), GB=counts.get("GB-MOV", 0),
                  requests=metadata["request_count"],
                  cycles=stats["memory_system"]["controller"]["cycles"],
                  peak=stats["frontend"]["physical_requests_peak_inflight"])
    print("BASELINE_RESULT " + json.dumps(result))


def simulation(path, recorder=None, install=True, **frontend_options):
    config = controller()
    if install:
        config["pud_placement_profile"] = "MIMDRAM_DDR4_8Gb_x8_v1"
    if recorder:
        config["controller_plugins"] = [dict(impl="CmdTraceRecorder", path=str(recorder))]
    return ramulator.Simulation(
        dict(impl="PuDTrace", clock_ratio=1, path=str(path), **frontend_options),
        dict(impl="GenericDRAM", clock_ratio=1,
             channel_mapper=dict(impl="CacheLineInterleave"), controllers=[config]))


def trace_file(tmp_path, body, header=None):
    path = tmp_path / "physical.trace"
    if header is None:
        header = "PUD_TRACE\nPROFILE " + placement_profile()["name"] + "\nRANKS 1\n"
    path.write_text(header + body)
    return path


@pytest.mark.parametrize("profile", PROFILES)
def test_complete_generated_trace(tmp_path, profile):
    metadata, path = write_gemv(profile, 1, 516, tmp_path)
    recorder = tmp_path / "commands.csv"
    sim = simulation(path, recorder)
    sim.run()
    stats = sim.stats
    sim.finalize()
    assert stats["frontend"]["physical_requests_submitted"] == metadata["request_count"]
    assert stats["frontend"]["physical_requests_completed"] == metadata["request_count"]
    assert stats["frontend"]["physical_requests_peak_inflight"] == 1
    with open(str(recorder)+".ch0") as stream:
        commands = list(csv.DictReader(stream))
    assert len(commands) == stats["frontend"]["physical_command_occurrences_completed"]
    assert len(commands) > metadata["request_count"]
    for opcode, count in metadata["request_counts"].items():
        name = opcode.lower().replace("-mov", "mov")
        assert stats["memory_system"][f"total_num_pud_{name}_requests"] == count
        assert stats["memory_system"]["controller"][f"num_pud_{name}_reqs_completed"] == count
    assert stats["memory_system"]["controller"]["cycles"] >= int(commands[-1]["clock"])
    print(profile, metadata["request_count"], len(commands),
          stats["memory_system"]["controller"]["cycles"])


def test_experiment_reports_separate_wall_times(tmp_path, monkeypatch):
    from experiments import pud_gemv_baseline as experiment

    ticks = iter((10.0, 12.5, 20.0, 24.0))
    monkeypatch.setattr(experiment, "perf_counter", lambda: next(ticks))
    result = experiment.run("MIMDRAM-InterMatFirst-int8", 1, 4, tmp_path)
    assert result["trace_generation_seconds"] == 2.5
    assert result["simulation_wall_seconds"] == 4.0
    assert result["controller_cycles"] > 0
    assert result["reduction_cycles_mean"] == 0  # N=4 has no physical reduction.
    assert result["mul_cycles_mean"] == result["chain_cycles_mean"] == result["controller_cycles"]
    assert result["start_delay_cycles_mean"] == 0
    assert result["chain_csv_path"] == ""
    assert not list(tmp_path.glob("*.chains.csv"))
    path = tmp_path / "results.csv"
    experiment.append_csv(path, result)
    with path.open(newline="", encoding="utf-8") as stream:
        row, = csv.DictReader(stream)
    assert float(row["trace_generation_seconds"]) == 2.5
    assert float(row["simulation_wall_seconds"]) == 4.0


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("m,n", [(2, 128), (8, 128), (2, 516)])
def test_experiment_chain_phases_preserve_execution(tmp_path, profile, m, n):
    from experiments import pud_gemv_baseline as experiment

    result = experiment.run(profile, m, n, tmp_path, chain_csv=True)
    layout = json.loads(Path(result["layout_json_path"]).read_text())
    trace = tmp_path / f"{profile}.trace"
    original_trace = trace.read_bytes()
    with Path(result["chain_csv_path"]).open() as stream:
        chains = [{key: int(value) for key, value in row.items()} for row in csv.DictReader(stream)]
    assert len(chains) == m
    assert {row["chain_id"] for row in chains} == {output["chain_id"] for output in layout["outputs"]}
    assert min(row["first_submit_cycle"] for row in chains) == 0
    assert max(row["final_complete_cycle"] for row in chains) == result["controller_cycles"]
    for row in chains:
        assert 0 <= row["first_submit_cycle"] <= row["mul_complete_cycle"] <= row["final_complete_cycle"]
        assert row["start_delay_cycles"] == row["first_submit_cycle"]
        assert row["mul_cycles"] == row["mul_complete_cycle"] - row["first_submit_cycle"]
        assert row["reduction_cycles"] == row["final_complete_cycle"] - row["mul_complete_cycle"]
        assert row["chain_cycles"] == row["final_complete_cycle"] - row["first_submit_cycle"]
        assert row["chain_cycles"] == row["mul_cycles"] + row["reduction_cycles"]
    assert all(result[key] == value for key, value in experiment.aggregate_latencies(chains).items())
    summary = tmp_path / "results.csv"
    experiment.append_csv(summary, result)
    with summary.open() as stream:
        summary_row, = csv.DictReader(stream)
    for key, value in experiment.aggregate_latencies(chains).items():
        assert float(summary_row[key]) == value

    # The same complete physical trace, with latency collection disabled.
    recorder = tmp_path / "uninstrumented.csv"
    reference = simulation(trace, recorder)
    reference.run()
    stats = reference.stats
    reference.finalize()
    assert stats["memory_system"]["controller"]["cycles"] == result["controller_cycles"]
    front = stats["frontend"]
    assert front["physical_requests_submitted"] == front["physical_requests_completed"] == result["physical_requests"]
    assert front["physical_requests_peak_inflight"] == result["peak_inflight_requests"]
    assert front["physical_command_occurrences_completed"] == result["issued_dram_commands"]
    assert Path(str(recorder) + ".ch0").read_bytes() == Path(result["command_trace_path"]).read_bytes()
    assert trace.read_bytes() == original_trace


def test_phase_percentiles_and_multidomain_rejection(tmp_path, monkeypatch):
    from experiments import pud_gemv_baseline as experiment

    rows = [dict(mul_cycles=v, reduction_cycles=v, chain_cycles=2*v, start_delay_cycles=0)
            for v in (0, 10)]
    result = experiment.aggregate_latencies(rows)
    assert result["mul_cycles_mean"] == result["mul_cycles_p50"] == 5
    assert result["mul_cycles_min"] == 0
    assert result["mul_cycles_max"] == 10
    assert result["mul_cycles_p95"] == 9.5
    assert result["mul_cycles_p99"] == 9.9
    assert result["chain_cycles_p99"] == 19.8
    monkeypatch.setattr(experiment, "write_gemv", lambda *args: pytest.fail("must reject before generation"))
    with pytest.raises(ValueError, match="one domain per chain"):
        experiment.run("MIMDRAM-InterMatFirst-int8", 2, 8196, tmp_path)


def test_checkpoint_timestamps_track_acceptance_and_full_callbacks(tmp_path):
    path = trace_file(tmp_path,
        "CHAIN 91\nNOT 0 0 0 0 0 0 10\n"
        "CHAIN 7\nNOT 0 0 0 0 1 1 20\n"
        "CHAIN 91\nNOT 0 0 0 0 0 0 11\nNOT 0 0 0 0 0 0 12\n")
    dut = _PuDTraceUnderTest(str(path), resolver(), [91, 7], [2, 1])
    assert dut.step(False) == 10
    assert dut.stats()["first_submit_cycles"] == [-1, -1]
    assert dut.step(True) == 20
    dut.complete(20, [1000])  # Occurrence issue clocks are not callback clocks.
    assert dut.step(False) == 10
    assert dut.step(True) == 10
    assert dut.stats()["first_submit_cycles"] == [3, 1]
    for _ in range(2):
        assert dut.step(True) == -1
    dut.complete(10, [1000])
    assert dut.step(True) == 11
    assert dut.step(True) == -1
    assert dut.stats()["checkpoint_complete_cycles"] == [-1, 2]
    dut.complete(11, [1000])
    assert dut.stats()["checkpoint_complete_cycles"] == [8, 2]
    # All delay before the reduction Request's acceptance belongs after the checkpoint.
    assert dut.step(False) == 12
    assert dut.step(False) == 12
    assert dut.step(True) == 12
    assert dut.stats()["final_complete_cycles"] == [-1, 2]
    assert dut.step(True) == -1
    dut.complete(12, [1000])
    assert dut.finished()
    from experiments.pud_gemv_baseline import chain_latencies
    chains = chain_latencies({"outputs": [{"chain_id": 91}, {"chain_id": 7}]}, dut.stats())
    assert chains[0] == dict(chain_id=91, first_submit_cycle=3, mul_complete_cycle=8,
                            final_complete_cycle=12, start_delay_cycles=3,
                            mul_cycles=5, reduction_cycles=4, chain_cycles=9)
    assert chains[1]["reduction_cycles"] == 0


@pytest.mark.parametrize("ids,checkpoints", [([91], []), ([], [1]), ([7], [1]),
    ([-1], [1]), ([91], [0]), ([91], [-1]), ([91], [2]), ([91, 91], [1, 1]), ([8], [1])])
def test_invalid_latency_checkpoints(tmp_path, ids, checkpoints):
    path = trace_file(tmp_path, "CHAIN 91\nNOT 0 0 0 0 0 0 10\nCHAIN 8\n")
    with pytest.raises(RuntimeError, match="PuDTrace"):
        _PuDTraceUnderTest(str(path), resolver(), ids, checkpoints)


def test_latency_requires_equal_clocks(tmp_path):
    path = trace_file(tmp_path, "CHAIN 0\nNOT 0 0 0 0 0 0 10\n")
    config = controller()
    config["pud_placement_profile"] = "MIMDRAM_DDR4_8Gb_x8_v1"
    with pytest.raises(RuntimeError, match="equal frontend and memory clock ratios"):
        ramulator.Simulation(dict(impl="PuDTrace", clock_ratio=2, path=str(path),
                                  latency_chain_ids=[0], latency_checkpoint_requests=[1]),
                             dict(impl="GenericDRAM", clock_ratio=1,
                                  channel_mapper=dict(impl="CacheLineInterleave"), controllers=[config]))


def test_checkpoint_includes_terminal_recovery(tmp_path):
    from ramulator._ramulator_test import _DeviceUnderTest

    path = trace_file(tmp_path, "CHAIN 42\nRowCopy 0 0 0 0 0 0 0 1\nNOT 0 0 0 0 0 0 1\n")
    recorder = tmp_path / "recovery.csv"
    sim = simulation(path, recorder, latency_chain_ids=[42], latency_checkpoint_requests=[1])
    sim.run()
    stats = sim.stats
    sim.finalize()
    with Path(str(recorder) + ".ch0").open() as stream:
        precharges = [int(row["clock"]) for row in csv.DictReader(stream) if row["command"] == "PREpb"]
    recovery = _DeviceUnderTest(controller()["dram"]).timings["nRP"]
    assert len(precharges) == 2
    assert stats["frontend"]["first_submit_cycles"] == [0]
    assert stats["frontend"]["checkpoint_complete_cycles"] == [precharges[0] + recovery]
    assert stats["frontend"]["final_complete_cycles"] == [precharges[1] + recovery]
    assert precharges[1] + recovery == stats["memory_system"]["controller"]["cycles"]


def test_location_translation_and_order(tmp_path):
    path = trace_file(tmp_path,
        "CHAIN 917\n"
        "RowCopy 0 0 0 0 0 1 1024 1025\n"
        "LC-MOV 0 0 0 0 0 1 1025 127 1026 0\n"
        "GB-MOV 0 0 0 0 1 2 1026 0 1027 3\n")
    recorder = tmp_path / "locations.csv"
    sim = simulation(path, recorder)
    sim.run()
    stats = sim.stats
    sim.finalize()
    with open(str(recorder)+".ch0") as stream:
        commands = list(csv.DictReader(stream))
    assert [int(c["type"]) for c in commands] == [2]*3 + [7]*6 + [8]*5
    assert [int(c["Row"]) for c in commands] == [
        1024, 1025, 1025, 1025, 1025, 1025, 1026, 1026, 1026,
        1026, 1027, 1026, 1027, 1027]
    assert [(c["command"], int(c["Column"])) for c in commands if c["command"] in ("RD_MOV", "WR_MOV")] == [
        ("RD_MOV", 127), ("WR_MOV", 0), ("RD_MOV", 0), ("WR_MOV", 3)]
    assert stats["memory_system"]["controller"]["pud_lcmov_moved_bits"] == 8
    assert stats["memory_system"]["controller"]["pud_gbmov_moved_bits"] == 4
    assert stats["frontend"]["physical_requests_completed"] == 3
    assert stats["frontend"]["physical_requests_peak_inflight"] == 1


@pytest.mark.parametrize("body", [
    "GEMV 0 0 0 0 0 0 0\n",
    "NOT 0 0 0 0 0 0\n",
    "NOT 0 0 0 0 0 0 0 junk\n",
    "NOT 0 0 0 0 0 0 0 9999999999999999999999999\n",
    "NOT 0 0 0 0 0 0 0 1\n",
    "NOT 0 0 0 0 -1 0 0\n",
    "LC-MOV 0 0 0 0 0 0 0 128 1 0\n",
    "LC-MOV 0 0 0 0 0 0 0 0 1\n",
    "GB-MOV 0 0 0 0 1 0 0 0 1 0\n",
    "RowCopy 0 0 0 0 0 0 0 1024\n",
])
def test_invalid_trace(tmp_path, body):
    with pytest.raises((RuntimeError, ValueError)):
        sim = simulation(trace_file(tmp_path, "CHAIN 0\n" + body))
        sim.run()


@pytest.mark.parametrize("header", [
    "INVALID_TRACE\n",
    "PUD_TRACE\nPROFILE other\nRANKS 1\n",
    "PUD_TRACE\nPROFILE " + placement_profile()["name"] + "\nRANKS 4\n",
])
def test_header_authority(tmp_path, header):
    with pytest.raises(RuntimeError):
        simulation(trace_file(tmp_path, "", header))


def test_empty_and_missing_resolver(tmp_path):
    path = trace_file(tmp_path, "")
    sim = simulation(path)
    sim.run()
    assert sim.stats["frontend"]["physical_requests_completed"] == 0
    with pytest.raises(RuntimeError, match="installed location resolver"):
        simulation(path, install=False)


def assert_generated_bank_overlap(metadata, physical, commands, k):
    assert [r["context"] for r in metadata["outputs"]] == [[0, 0, 0, bank] for bank in (0, 1)]
    assert [r["domains"][0]["mat_begin"] for r in metadata["outputs"]] == [0, 0]
    assert all(d["mat_count"] == k for r in metadata["outputs"] for d in r["domains"])
    end = metadata["outputs"][0]["domains"][-1]["completion_index"]
    for start, bank in ((0, 0), (end, 1)):
        fields = physical[start].split()
        assert fields[:7] == ["RowCopy", "0", "0", "0", str(bank), "0", str(k-1)]
    assert all([int(c[level]) for level in ("Channel", "Rank", "BankGroup")] == [0]*3
               and int(c["Bank"]) in (0, 1)
               and int(c["Row"]) < 1024 for c in commands)
    # Both chains' first Requests are single-destination RowCopy. With one
    # outstanding Request per chain, two source ACTs before either PRE prove
    # that the generated bank-striped outputs execute concurrently.
    first_pre = next(i for i, c in enumerate(commands) if c["command"] == "PREpb")
    starts = [int(c["clock"]) for c in commands[:first_pre]
              if c["command"] == "ACT_PUD_S_OC"]
    assert len(starts) == 2
    assert max(starts) < int(commands[first_pre]["clock"])


@pytest.mark.parametrize("profile", PROFILES)
def test_generated_chains_preserve_stream_and_overlap(tmp_path, profile):
    metadata, path = write_gemv(profile, 2, 12, tmp_path)
    lines = path.read_text().splitlines()
    assert lines[0] == "PUD_TRACE"
    assert [line for line in lines if line.startswith("CHAIN ")] == ["CHAIN 0", "CHAIN 1"]
    physical = [line for line in lines[3:] if not line.startswith("CHAIN ")]
    assert len(physical) == metadata["request_count"]
    assert Counter(line.split()[0] for line in physical) == metadata["request_counts"]
    first_end = metadata["outputs"][0]["domains"][-1]["completion_index"]
    assert lines[4:4+first_end] == physical[:first_end]
    assert lines[5+first_end:] == physical[first_end:]
    assert metadata["outputs"][-1]["domains"][-1]["completion_index"] == len(physical)
    recorder = tmp_path / "concurrent.csv"
    sim = simulation(path, recorder)
    sim.run()
    stats = sim.stats
    sim.finalize()
    front = stats["frontend"]
    assert front["physical_requests_peak_inflight"] == 2
    assert front["physical_requests_submitted"] == front["physical_requests_completed"] == len(physical)
    with open(str(recorder)+".ch0") as stream:
        commands = list(csv.DictReader(stream))
    assert len(commands) == front["physical_command_occurrences_completed"]
    assert_generated_bank_overlap(metadata, physical, commands, 1)
    report_baseline(metadata, stats)
    for opcode, count in metadata["request_counts"].items():
        name = opcode.lower().replace("-mov", "mov")
        assert stats["memory_system"][f"total_num_pud_{name}_requests"] == count
        assert stats["memory_system"]["controller"][f"num_pud_{name}_reqs_completed"] == count

    # Both executions use exactly the same current physical Request stream.
    serialized = trace_file(tmp_path, "CHAIN 0\n" + "\n".join(physical)+"\n")
    assert serialized.read_text().splitlines()[4:] == physical
    reference = simulation(serialized)
    reference.run()
    reference_stats = reference.stats
    reference.finalize()
    assert reference_stats["frontend"]["physical_requests_peak_inflight"] == 1
    for field in ("physical_requests_submitted", "physical_requests_completed",
                  "physical_command_occurrences_completed"):
        assert reference_stats["frontend"][field] == front[field]
    print(profile, "serialized", reference_stats["memory_system"]["controller"]["cycles"], "concurrent",
          stats["memory_system"]["controller"]["cycles"], "peak", front["physical_requests_peak_inflight"])


@pytest.mark.parametrize("profile", PROFILES)
def test_generated_neighbor_ranges_execute_concurrently(tmp_path, profile):
    metadata, path = write_gemv(profile, 2, 516, tmp_path)
    physical = [line for line in path.read_text().splitlines()[3:] if not line.startswith("CHAIN ")]
    assert {(int(f[4]), int(f[5]), int(f[6])) for line in physical
            if (f := line.split())[0] == "GB-MOV"} == {(0, 0, 1), (1, 0, 1)}
    recorder = tmp_path / "ranges.csv"
    sim = simulation(path, recorder)
    sim.run()
    stats = sim.stats
    sim.finalize()
    with open(str(recorder)+".ch0") as stream:
        commands = list(csv.DictReader(stream))
    assert_generated_bank_overlap(metadata, physical, commands, 2)
    front = stats["frontend"]
    assert front["physical_requests_submitted"] == front["physical_requests_completed"] == metadata["request_count"]
    assert front["physical_command_occurrences_completed"] == len(commands)
    assert front["physical_requests_peak_inflight"] == 2
    for opcode, count in metadata["request_counts"].items():
        name = opcode.lower().replace("-mov", "mov")
        assert stats["memory_system"]["controller"][f"num_pud_{name}_reqs_completed"] == count
    report_baseline(metadata, stats)


@pytest.mark.parametrize("profile", [p for p in PROFILES if "IntraMatFirst" in p])
def test_generated_ranged_local_reduction(tmp_path, profile):
    metadata, path = write_gemv(profile, 2, 1024, tmp_path)
    sim = simulation(path)
    sim.run()
    stats = sim.stats
    sim.finalize()
    assert stats["frontend"]["physical_requests_completed"] == metadata["request_count"]
    counts = metadata["request_counts"]
    assert stats["memory_system"]["controller"]["pud_lcmov_moved_bits"] == counts["LC-MOV"]*2*4
    assert stats["memory_system"]["controller"]["pud_gbmov_moved_bits"] == counts["GB-MOV"]*4


@pytest.mark.parametrize("index", [0, 1, 4, 15, 16, 128, 1024, 65536, 17*65536-1])
def test_placement_context_requests_resolve_and_complete(tmp_path, index):
    context, subarray, base, mats = _output_placement(placement_profile(), 2, 60, index)
    row = subarray*1024 + base
    prefix = " ".join(map(str, context))
    # Sample each capacity boundary with compute, LC and the required GB edge.
    path = trace_file(tmp_path,
        f"CHAIN 0\nRowCopy {prefix} {mats[0]} {mats[-1]} {row} {row+1}\n"
        f"LC-MOV {prefix} {mats[-1]} {mats[-1]} {row+1} 127 {row+2} 0\n"
        f"GB-MOV {prefix} {mats[0]} {mats[-1]} {row} 0 {row+2} 127\n")
    sim = simulation(path)
    sim.run()
    stats = sim.stats
    sim.finalize()
    assert stats["frontend"]["physical_requests_completed"] == 3
    assert stats["frontend"]["physical_command_occurrences_completed"] == 14


def test_callback_order_retry_and_fairness(tmp_path):
    path = trace_file(tmp_path,
        "CHAIN 91\nNOT 0 0 0 0 0 0 10\n"
        "CHAIN 7\nNOT 0 0 0 0 1 1 20\nNOT 0 0 0 0 1 1 21\n"
        "CHAIN 91\nNOT 0 0 0 0 0 0 11\nNOT 0 0 0 0 0 0 12\n")
    dut = _PuDTraceUnderTest(str(path), resolver())
    assert dut.step(False) == 10
    assert dut.stats()["physical_requests_peak_inflight"] == 0
    assert dut.step(True) == 20  # Rejection cannot monopolize injection.
    dut.complete(20, [1, -1, 2])
    assert dut.step(False) == 10  # Completion joins behind already-ready work.
    assert dut.step(True) == 21
    assert dut.step(False) == 10
    assert dut.step(True) == 10  # Same head survives repeated backpressure.
    assert dut.stats()["physical_requests_peak_inflight"] == 2
    for _ in range(3):
        assert dut.step(True) == -1  # No successor before full callback.
    dut.complete(21, [3, 4])  # Independent chain can finish first.
    assert not dut.finished()
    assert dut.step(True) == -1
    dut.complete(10, [5, 6])
    assert dut.step(True) == 11
    assert dut.step(True) == -1
    dut.complete(11, [7, 8])
    assert dut.step(True) == 12
    assert not dut.finished()  # Last admission is not last completion.
    dut.complete(12, [9, 10])
    assert dut.finished()
    assert dut.step(True) == -1
    stats = dut.stats()
    assert stats["physical_requests_submitted"] == stats["physical_requests_completed"] == 5
    assert stats["physical_command_occurrences_completed"] == 10


def test_independent_ranges_execute_concurrently(tmp_path):
    path = trace_file(tmp_path,
        "CHAIN 42\nRowCopy 0 0 0 0 0 0 0 1\nNOT 0 0 0 0 0 0 1\n"
        "CHAIN 9\nRowCopy 0 0 0 0 1 1 2 3\nNOT 0 0 0 0 1 1 3\n")
    recorder = tmp_path / "overlap.csv"
    sim = simulation(path, recorder)
    sim.run()
    stats = sim.stats
    sim.finalize()
    with open(str(recorder)+".ch0") as stream:
        commands = list(csv.DictReader(stream))
    copies = [c for c in commands if int(c["type"]) == REQUEST_TYPE_IDS["RowCopy"]]
    starts = [int(c["clock"]) for c in copies if int(c["Row"]) in (0, 2)]
    closes = [int(c["clock"]) for c in copies if c["command"] == "PREpb"]
    assert len(starts) == len(closes) == 2
    assert max(starts) < min(closes)  # Both execute before either terminal PRE.
    assert stats["frontend"]["physical_requests_peak_inflight"] == 2
    assert stats["frontend"]["physical_requests_completed"] == 4
    assert stats["frontend"]["physical_command_occurrences_completed"] == len(commands)


@pytest.mark.parametrize("body", [
    "NOT 0 0 0 0 0 0 0\n", "CHAIN\n", "CHAIN -1\n", "CHAIN 1 2\n",
    "CHAIN x\n", "CHAIN 2147483648\n", "CHAIN 3\nGEMV 0\n",
])
def test_invalid_chain_trace(tmp_path, body):
    with pytest.raises(RuntimeError):
        simulation(trace_file(tmp_path, body))


@pytest.mark.parametrize("body", ["", "CHAIN 8\nCHAIN 2\nCHAIN 8\n"])
def test_empty_chain_trace(tmp_path, body):
    sim = simulation(trace_file(tmp_path, body))
    sim.run()
    assert sim.stats["frontend"]["physical_requests_peak_inflight"] == 0
    assert sim.stats["frontend"]["physical_requests_completed"] == 0
    sim.finalize()
