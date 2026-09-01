import pytest

import ramulator
from ramulator._ramulator_test import _DeviceUnderTest
from ramulator.dram.spec import CONTROLLER_SEQUENCED
import tests.device_timings.harness as device_timings


def make_dut(dram_class):
    dram = dram_class(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    return device_timings.DeviceUnderTest(dram)


def test_ddr4_pud_conventional_baseline_matches_ddr4():
    ddr4 = make_dut(ramulator.dram.DDR4)
    pud = make_dut(ramulator.dram.DDR4_PuD)

    assert pud.level_names == ddr4.level_names
    assert pud.command_names == ddr4.command_names
    assert pud.timings == ddr4.timings

    for dut in (ddr4, pud):
        addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=12, Column=0)
        assert dut.probe("RD", addr, clk=0).preq == "ACT"
        assert dut.probe("WR", addr, clk=0).preq == "ACT"
        dut.issue("ACT", addr, clk=0)
        assert dut.probe("RD", addr, clk=dut.timings["nRCD"]).ready is True
        assert dut.probe("WR", addr, clk=dut.timings["nRCD"]).ready is True


def test_ddr4_pud_mutable_definitions_are_independent():
    mutable_names = (
        "levels",
        "commands",
        "states",
        "timing_params",
        "supported_requests",
        "timing_constraints",
        "command_cycles",
        "row_commands",
        "column_commands",
        "org_presets",
        "timing_presets",
        "geometry",
    )

    for name in mutable_names:
        assert getattr(ramulator.dram.DDR4_PuD, name) is not getattr(ramulator.dram.DDR4, name)


def test_ddr4_pud_uses_named_controller_sequenced_marker():
    for request_name in ("RowCopy", "MAJ3", "MAJ5", "NOT"):
        assert ramulator.dram.DDR4_PuD.supported_requests[request_name] is CONTROLLER_SEQUENCED


def test_legacy_none_request_target_is_rejected(monkeypatch):
    supported_requests = dict(ramulator.dram.DDR4_PuD.supported_requests)
    supported_requests["RowCopy"] = None
    monkeypatch.setattr(ramulator.dram.DDR4_PuD, "supported_requests", supported_requests)

    with pytest.raises(ValueError, match="CONTROLLER_SEQUENCED instead of None"):
        ramulator.dram.DDR4_PuD.validate()


@pytest.mark.parametrize(
    ("rows_per_subarray", "message"),
    [
        (0, "rows_per_subarray must be positive"),
        (1000, "rows_per_subarray must divide"),
    ],
)
def test_ddr4_pud_rejects_invalid_subarray_geometry(rows_per_subarray, message):
    dram = ramulator.dram.DDR4_PuD(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    config = dram.to_config()
    config["geometry"]["rows_per_subarray"] = rows_per_subarray

    with pytest.raises(RuntimeError, match=message):
        _DeviceUnderTest(config)
