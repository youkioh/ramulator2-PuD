"""Versioned trace authority, per-controller admission, and runtime reporting."""
import csv
from collections import Counter
import pytest
import ramulator
from ramulator._ramulator_test import _PuDTraceUnderTest, _LocationResolverUnderTest
from tests.unit_tests.test_pud_location import CONTEXT
from tools.pud_gemv_generator.generator import placement_profile
from tools.pud_gemv_generator.targets import target_config


def header(target):
    g = placement_profile(target)
    return (f"PUD_TRACE 2\nPROFILE {g['name']}\nBANK_LEVELS " + " ".join(g["bank_levels"])
            + "\nBANK_SIZES " + " ".join(map(str,g["bank_sizes"])) + "\n")


def simulation(target, path, recorder=None, interleave_bits=0, controllers=None):
    c = target_config(target)
    config = dict(impl=c["controller"], dram=c["dram"].to_config(),
        pud_placement_profile=c["profile"], scheduler=dict(impl="FRFCFS"),
        refresh_manager=dict(impl="AllBank"), row_policy=dict(impl="Open"),
        addr_mapper=dict(impl="RoBaRaCoCh"))
    if recorder:
        config["controller_plugins"] = [dict(impl="CmdTraceRecorder",path=str(recorder))]
    return ramulator.Simulation(dict(impl="PuDTrace",clock_ratio=1,path=str(path)),
        dict(impl="GenericDRAM",clock_ratio=1,
             channel_mapper=dict(impl="CacheLineInterleave",interleave_bits=interleave_bits),
             controllers=controllers if controllers is not None else [config]*c["channels"]))


@pytest.mark.parametrize("target",["GDDR7","HBM3"])
def test_cross_controller_chain_and_global_command_identity(target,tmp_path):
    g = placement_profile(target)
    path, recorder = tmp_path/"input.trace",tmp_path/"commands.csv"
    body = "CHAIN 5\n"
    for channel in range(g["bank_sizes"][0]):
        context = " ".join(map(str,[channel]+[0]*(len(g["bank_levels"])-1)))
        body += f"NOT {context} 0 0 {10+channel}\n"
    path.write_text(header(target)+body)
    sim = simulation(target,path,recorder)
    sim.run()
    front = sim.stats["frontend"]
    sim.finalize()
    assert front["physical_requests_completed"] == g["bank_sizes"][0]
    assert front["physical_requests_peak_inflight"] == 1
    previous_close = -1
    for channel in range(g["bank_sizes"][0]):
        with open(str(recorder)+f".ch{channel}") as stream:
            commands = list(csv.DictReader(stream))
        assert len(commands) == 3
        assert {int(row["Channel"]) for row in commands} == {channel}
        assert int(commands[0]["clock"]) > previous_close
        previous_close = int(commands[-1]["clock"])


@pytest.mark.parametrize("target",["GDDR7","HBM3"])
def test_attempt_budget_rejection_rotation_and_completion(target,tmp_path):
    selected = target_config(target)
    count = selected["channels"]
    resolver = _LocationResolverUnderTest(selected["dram"].to_config(),dict(CONTEXT,channels=count))
    depth = len(placement_profile(target)["bank_levels"])
    def line(channel,row):
        context = " ".join(map(str,[channel]+[0]*(depth-1)))
        return f"NOT {context} 0 0 {row}\n"
    path = tmp_path/"admission.trace"
    path.write_text(header(target)+"CHAIN 91\n"+line(0,10)+line(1,11)
        +"CHAIN 7\n"+line(0,20)+"CHAIN 8\n"+line(1,30)
        +"CHAIN 2\n"+line(0,40)+"CHAIN 4\n"+line(2,50))
    dut = _PuDTraceUnderTest(str(path),resolver)
    assert dut.step_channels([False]+[True]*(count-1)) == [[0,10],[1,30],[2,50]]
    assert dut.stats()["physical_requests_submitted"] == 2
    assert dut.step_channels([True]*count) == [[0,20]]
    assert dut.step_channels([True]*count) == [[0,40]]
    assert dut.step_channels([True]*count) == [[0,10]]
    dut.complete(10,[1,2,3])
    assert dut.step_channels([True]*count) == [[1,11]]
    assert dut.step_channels([True]*count) == []
    for row in (11,20,30,40,50):
        dut.complete(row,[1,2,3])
    assert dut.finished()
    assert dut.stats()["physical_requests_completed"] == 6
    assert dut.stats()["physical_command_occurrences_completed"] == 18


@pytest.mark.parametrize("target",["GDDR7","HBM3"])
def test_persistent_rejection_rotates_to_same_controller_peers(target,tmp_path):
    selected = target_config(target)
    count = selected["channels"]
    resolver = _LocationResolverUnderTest(selected["dram"].to_config(),dict(CONTEXT,channels=count))
    depth = len(placement_profile(target)["bank_levels"])
    context = " ".join(["0"]*depth)
    path = tmp_path/"retry.trace"
    path.write_text(header(target)+"".join(
        f"CHAIN {row}\nNOT {context} 0 0 {row}\n" for row in (10,20,30)))
    dut = _PuDTraceUnderTest(str(path),resolver)
    for row in (10,20,30,10,20,30):
        assert dut.step_channels([False]*count) == [[0,row]]
    for row in (10,20,30):
        assert dut.step_channels([True]*count) == [[0,row]]
        dut.complete(row,[1,2,3])
    assert dut.finished()


@pytest.mark.parametrize("target",["GDDR7","HBM3"])
def test_all_controllers_attempt_in_one_tick(target,tmp_path):
    selected = target_config(target)
    count = selected["channels"]
    resolver = _LocationResolverUnderTest(selected["dram"].to_config(),dict(CONTEXT,channels=count))
    depth = len(placement_profile(target)["bank_levels"])
    path = tmp_path/"all.trace"
    body = header(target)
    for channel in range(count):
        context = " ".join(map(str,[channel]+[0]*(depth-1)))
        body += f"CHAIN {channel}\nNOT {context} 0 0 {10+channel}\n"
    path.write_text(body)
    dut = _PuDTraceUnderTest(str(path),resolver)
    assert dut.step_channels([True]*count) == [[c,10+c] for c in range(count)]
    assert dut.step_channels([True]*count) == []
    for channel in range(count):
        dut.complete(10+channel,[1,2,3])
    assert dut.finished()
    assert dut.stats()["physical_requests_completed"] == count


@pytest.mark.parametrize("target",["GDDR7","HBM3"])
@pytest.mark.parametrize("mutation",["version","profile","levels","reorder","sizes","zero","extra","legacy"])
def test_malformed_header(target,mutation,tmp_path):
    lines = header(target).splitlines()
    if mutation == "version": lines[0] = "PUD_TRACE 3"
    if mutation == "profile": lines[1] += " alias"
    if mutation == "levels": lines[2] += " Column"
    if mutation == "reorder": lines[2] = "BANK_LEVELS " + " ".join(reversed(lines[2].split()[1:]))
    if mutation == "sizes": lines[3] = "BANK_SIZES 1 16"
    if mutation == "zero": lines[3] = "BANK_SIZES " + " ".join("0" for _ in lines[3].split()[1:])
    if mutation == "extra": lines[3] += " 1"
    if mutation == "legacy": lines = ["PUD_TRACE",lines[1],"RANKS 0"]
    path = tmp_path/"bad.trace"
    path.write_text("\n".join(lines)+"\n")
    with pytest.raises(RuntimeError): simulation(target,path)


@pytest.mark.parametrize("target",["GDDR7","HBM3"])
@pytest.mark.parametrize("operands",["NOT {c} 0 0 10 11","NOT {c} 0 0 -1", "NOT {c} 0 0 2147483648",
    "NOT {c} 1 0 10", "MAJ3 {c} 0 0 10 10 11", "LC-MOV {c} 0 0 10 999 11 0",
    "GB-MOV {c} 0 2 10 0 11 0"])
def test_malformed_request(target,operands,tmp_path):
    depth = len(placement_profile(target)["bank_levels"])
    path = tmp_path/"bad.trace"
    path.write_text(header(target)+"CHAIN 0\n"+operands.format(c=" ".join(["0"]*depth))+"\n")
    with pytest.raises((RuntimeError,ValueError)):
        sim = simulation(target,path)
        try: sim.run()
        finally: sim.finalize()


@pytest.mark.parametrize("target",["GDDR7","HBM3"])
def test_actual_interleave_setting_rejected(target,tmp_path):
    path = tmp_path/"empty.trace"
    path.write_text(header(target))
    with pytest.raises((RuntimeError,ValueError),match="mapper"):
        simulation(target,path,interleave_bits=1)


@pytest.mark.parametrize("target",["GDDR7","HBM3"])
def test_runner_aggregates_counts_not_clocks(target,tmp_path):
    from experiments.pud_gemv_baseline import run
    g = placement_profile(target)
    result = run("MIMDRAM-InterMatFirst-int8",4*g["mats_per_chip"]+1,128,tmp_path,target=target,chain_csv=True)
    assert result["physical_chains"] == result["active_controllers"] == 2
    assert result["packing_factor"] == 4
    assert result["fused_range_widths"] == [g["mats_per_chip"],1]
    assert len(result["per_channel"]) == g["bank_sizes"][0]
    assert result["issued_dram_commands"] == sum(sum(c["commands"].values()) for c in result["per_channel"])
    assert result["maintenance_command_count"] > 0
    assert not any(name.startswith("RFM") for name in result["maintenance_commands"])
    assert result["controller_cycles"] == result["pud_in_memory_phase_ticks"]
    assert result["pud_in_memory_phase_ns"] == result["controller_cycles"]*result["tick_duration_ps"]/1000
    assert result["residual_values_per_output"] == g["hffs_per_mat"]
    assert result["host_add_calls"] == result["M"]*(g["hffs_per_mat"]+1)
    assert len({r["final_complete_cycle"] for r in result["output_completion_observations"][:4]}) == 1
