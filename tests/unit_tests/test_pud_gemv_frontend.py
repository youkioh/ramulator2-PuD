"""Thin frontend integration over the existing unified-substrate test setup."""
import csv
from collections import Counter
import pytest
import ramulator
from ramulator._ramulator_test import _PuDTraceUnderTest
from ramulator.dram.spec import REQUEST_TYPE_IDS
from tools.pud_gemv_generator.generator import PROFILES, placement_profile, write_gemv
from tests.unit_tests.test_pud_request_locations import controller
from tests.unit_tests.test_pud_location import resolver


def simulation(path, recorder=None, install=True):
    config = controller()
    if install:
        config["pud_placement_profile"] = "MIMDRAM_DDR4_8Gb_x8_v1"
    if recorder:
        config["controller_plugins"] = [dict(impl="CmdTraceRecorder", path=str(recorder))]
    return ramulator.Simulation(
        dict(impl="PuDTrace", clock_ratio=1, path=str(path)),
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
        assert len(list(csv.DictReader(stream))) == front["physical_command_occurrences_completed"]
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
