"""Thin frontend integration over the existing unified-substrate test setup."""
import csv
import pytest
import ramulator
from tools.pud_gemv_generator.generator import PROFILES, placement_profile, write_gemv
from tests.unit_tests.test_pud_request_locations import controller


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
        header = "PUD_TRACE 1\nPROFILE " + placement_profile()["name"] + "\nRANKS 1\n"
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
        sim = simulation(trace_file(tmp_path, body))
        sim.run()


@pytest.mark.parametrize("header", [
    "PUD_TRACE 2\n",
    "PUD_TRACE 1\nPROFILE other\nRANKS 1\n",
    "PUD_TRACE 1\nPROFILE " + placement_profile()["name"] + "\nRANKS 4\n",
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
