"""GEMM uses unchanged CHAIN ordering and band-completion instrumentation."""
import csv

from ramulator._ramulator_test import _DeviceUnderTest, _PuDTraceUnderTest
from experiments.pud_gemm import _configuration, _simulate
from tools.pud_gemm_generator.generator import _generate, _write_artifacts
from tools.pud_gemv_generator.generator import trace_header
from tests.unit_tests.test_pud_gemv_frontend import simulation
from tests.unit_tests.test_pud_request_locations import controller
from tests.unit_tests.test_pud_location import resolver


def test_generated_two_bank_band_completion_and_accounting(tmp_path):
    layout, trace = _generate("MIMDRAM-InterMatFirst-int8", banks=(0, 1))
    path = _write_artifacts(layout, trace, tmp_path)
    result = _simulate(layout, path)
    assert result["physical_chains"] == 2
    assert result["physical_requests"] == len(trace)
    assert result["peak_inflight_requests"] == 2
    assert result["issued_command_occurrences"] == result["physical_command_occurrences_completed"]
    assert result["logical_outputs"] == 2048
    assert len({o["output_id"] for o in result["output_completion_observations"]}) == 2048
    chains = {c["chain_id"]: c for c in result["chains"]}
    for output in result["output_completion_observations"]:
        assert output["complete_cycle"] == chains[output["chain_id"]][f"band{output['band']}_complete_cycle"]
    assert not any("mul_cycles" in c or "reduction_cycles" in c for c in result["chains"])
    with open(str(path.with_suffix(".commands.csv"))+".ch0") as stream:
        commands = list(csv.DictReader(stream))
    recovery = _DeviceUnderTest(controller()["dram"]).timings["nRP"]
    for chain in layout["chains"]:
        bank = chain["chain_id"]
        local = [r for r in commands if int(r["Bank"]) == bank and int(r["BankGroup"]) == 0]
        closes = [i for i, r in enumerate(local) if r["command"] == "PREpb"]
        # LC has an intermediate PRE as well as its terminal PRE. Count both
        # occurrences to locate the band's final recovery boundary accurately.
        band0 = trace[chain["first_request_index"]-1:
                      chain["first_request_index"]-1+chain["checkpoint_request"]]
        pre_count = sum(2 if line.startswith("LC-MOV") else 1 for line in band0)
        last_band0_pre = closes[pre_count-1]
        assert chains[bank]["band0_complete_cycle"] == int(local[last_band0_pre]["clock"])+recovery
        assert int(local[last_band0_pre+1]["clock"]) >= chains[bank]["band0_complete_cycle"]
    assert max(c["first_submit_cycle"] for c in chains.values()) < min(c["band0_complete_cycle"] for c in chains.values())


def test_unequal_banks_have_no_global_band_barrier(tmp_path):
    layout, _ = _generate("MIMDRAM-InterMatFirst-int8", banks=(0, 1), local_outputs=1)
    path = tmp_path/"bands.trace"
    # Nonmonotonic IDs are intentionally unrelated to Bank identity. Bank 1
    # has a longer band 0, so Bank 0's band 1 must not wait for it.
    path.write_text(trace_header(layout)+
        "CHAIN 91\nNOT 0 0 0 0 0 127 10\nNOT 0 0 0 0 0 127 70\n"
        "CHAIN 7\nNOT 0 0 0 1 0 127 20\nNOT 0 0 0 1 0 127 21\n"
        "NOT 0 0 0 1 0 127 22\nNOT 0 0 0 1 0 127 80\n")
    recorder = tmp_path/"unequal.csv"
    sim = simulation(path, recorder, latency_chain_ids=[91, 7], latency_checkpoint_requests=[1, 3])
    sim.run()
    front = sim.stats["frontend"]
    sim.finalize()
    assert front["physical_requests_submitted"] == front["physical_requests_completed"] == 6
    assert front["physical_command_occurrences_completed"] == 18
    with open(str(recorder)+".ch0") as stream:
        commands = list(csv.DictReader(stream))
    start_band1 = next(int(r["clock"]) for r in commands if int(r["Bank"]) == 0 and int(r["Row"]) == 70)
    assert front["checkpoint_complete_cycles"][0] <= start_band1 < front["checkpoint_complete_cycles"][1]
    assert front["physical_requests_peak_inflight"] == 2

    # Deterministic rejection/callback exercise: the successor is not eligible
    # merely because its predecessor was accepted; independent banks progress.
    dut = _PuDTraceUnderTest(str(path), resolver(), [91, 7], [1, 3])
    assert dut.step(False) == 10
    assert dut.step(True) == 20
    assert dut.step(True) == 10
    assert dut.step(True) == -1
    dut.complete(10, [0, 1, 2])
    assert dut.step(False) == 70
    assert dut.step(True) == 70
    dut.complete(70, [3, 4, 5])
    assert not dut.finished()
    for row, successor in ((20, 21), (21, 22), (22, 80)):
        dut.complete(row, [0, 1, 2])
        assert dut.step(True) == successor
    dut.complete(80, [0, 1, 2])
    assert dut.finished()
    assert dut.stats()["physical_requests_submitted"] == dut.stats()["physical_requests_completed"] == 6


def test_configuration_has_no_dependency_extension(tmp_path):
    layout, _ = _generate("MIMDRAM-InterMatFirst-int8", banks=(0,), local_outputs=1)
    frontend, _, _ = _configuration(layout, tmp_path/"x.trace", tmp_path/"commands.csv")
    config = frontend.to_config()
    assert set(config) == {"impl", "clock_ratio", "path", "latency_chain_ids", "latency_checkpoint_requests"}
    assert config["latency_checkpoint_requests"] == [layout["chains"][0]["checkpoint_request"]]
