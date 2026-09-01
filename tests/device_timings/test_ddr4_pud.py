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
    assert pud.command_names[:len(ddr4.command_names)] == ddr4.command_names
    assert pud.timings == ddr4.timings

    for dut in (ddr4, pud):
        addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=12, Column=0)
        assert dut.probe("RD", addr, clk=0).preq == "ACT"
        assert dut.probe("WR", addr, clk=0).preq == "ACT"
        dut.issue("ACT", addr, clk=0)
        assert dut.probe("RD", addr, clk=dut.timings["nRCD"]).ready is True
        assert dut.probe("WR", addr, clk=dut.timings["nRCD"]).ready is True


def test_ddr4_pud_registers_phase3_commands_and_states():
    dram = ramulator.dram.DDR4_PuD(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    dut = _DeviceUnderTest(dram.to_config())

    assert dut.command_names == [
        *ramulator.dram.DDR4.commands,
        "ACT_PUD",
        "ACT_PUD_OC",
        "ACT_PUD_S",
        "ACT_PUD_S_OC",
        "N",
    ]
    assert dut.state_names == [
        *ramulator.dram.DDR4.states,
        "PuDChargeSharing",
        "PuDSensed",
    ]


@pytest.mark.parametrize(
    "command",
    ("ACT_PUD", "ACT_PUD_OC", "ACT_PUD_S", "ACT_PUD_S_OC"),
)
def test_ddr4_pud_activation_command_metadata_and_handlers_are_registered(command):
    dram = ramulator.dram.DDR4_PuD(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    info = _DeviceUnderTest(dram.to_config()).command_info(command)

    assert info == {
        "is_opening": True,
        "is_closing": False,
        "is_accessing": False,
        "is_refreshing": False,
        "bank_target": "Single",
        "has_action": True,
        "has_preq": True,
        "has_rowhit": False,
        "has_rowopen": False,
    }


def test_ddr4_pud_n_command_metadata_and_handlers_are_registered_without_internal_phases():
    dram = ramulator.dram.DDR4_PuD(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    dut = _DeviceUnderTest(dram.to_config())

    assert [name for name in dut.command_names if name == "N"] == ["N"]
    assert dut.command_info("N") == {
        "is_opening": False,
        "is_closing": False,
        "is_accessing": False,
        "is_refreshing": False,
        "bank_target": "Single",
        "has_action": True,
        "has_preq": True,
        "has_rowhit": False,
        "has_rowopen": False,
    }


def test_ddr4_pud_rowcopy_device_transitions_support_repeated_destinations():
    dut = make_dut(ramulator.dram.DDR4_PuD)
    source = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    destinations = [
        dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=row, Column=0)
        for row in (20, 21, 22)
    ]

    dut.issue("ACT_PUD_S_OC", source, clk=0)
    for clk, destination in enumerate(destinations, start=1):
        assert dut.probe("ACT_PUD", destination, clk=clk).ready is True
        dut.issue("ACT_PUD", destination, clk=clk)

    assert dut.probe("N", destinations[-1], clk=4).ready is True
    dut.issue("PREpb", destinations[-1], clk=4)
    assert dut.probe("RD", source, clk=5).preq == "ACT"


@pytest.mark.parametrize("additional_activations", (1, 3))
def test_ddr4_pud_majority_device_transitions(additional_activations):
    dut = make_dut(ramulator.dram.DDR4_PuD)
    rows = [
        dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=row, Column=0)
        for row in range(30, 32 + additional_activations)
    ]

    dut.issue("ACT_PUD_OC", rows[0], clk=0)
    for clk, row in enumerate(rows[1:-1], start=1):
        dut.issue("ACT_PUD", row, clk=clk)
    dut.issue("ACT_PUD_S", rows[-1], clk=additional_activations + 1)
    dut.issue("PREpb", rows[-1], clk=additional_activations + 2)

    assert dut.probe("ACT_PUD_OC", rows[0], clk=additional_activations + 3).ready is True


def test_ddr4_pud_not_device_transitions():
    dut = make_dut(ramulator.dram.DDR4_PuD)
    source = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=40, Column=0)

    dut.issue("ACT_PUD_S_OC", source, clk=0)
    dut.issue("N", source, clk=1)
    assert dut.probe("ACT_PUD", source, clk=2).ready is True
    dut.issue("PREpb", source, clk=2)

    assert dut.probe("ACT_PUD_S_OC", source, clk=3).ready is True


@pytest.mark.parametrize("command", ("ACT_PUD", "ACT_PUD_S", "N"))
def test_ddr4_pud_rejects_nonopening_pud_commands_while_closed(command):
    dut = make_dut(ramulator.dram.DDR4_PuD)
    addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=50, Column=0)

    with pytest.raises(RuntimeError, match="Invalid bank state"):
        dut.probe(command, addr, clk=0)


@pytest.mark.parametrize("command", ("ACT_PUD_OC", "ACT_PUD_S_OC", "N", "PREpb"))
def test_ddr4_pud_rejects_illegal_commands_while_charge_sharing(command):
    dut = make_dut(ramulator.dram.DDR4_PuD)
    addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=60, Column=0)
    dut.issue("ACT_PUD_OC", addr, clk=0)

    with pytest.raises(RuntimeError, match="Invalid bank state"):
        dut.probe(command, addr, clk=1)


@pytest.mark.parametrize("command", ("ACT_PUD_OC", "ACT_PUD_S_OC", "ACT_PUD_S"))
def test_ddr4_pud_rejects_illegal_pud_activations_while_sensed(command):
    dut = make_dut(ramulator.dram.DDR4_PuD)
    addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=70, Column=0)
    dut.issue("ACT_PUD_S_OC", addr, clk=0)

    with pytest.raises(RuntimeError, match="Invalid bank state"):
        dut.probe(command, addr, clk=1)


@pytest.mark.parametrize("phase_command", ("ACT_PUD_OC", "ACT_PUD_S_OC"))
@pytest.mark.parametrize("conventional_command", ("ACT", "RD", "WR"))
def test_ddr4_pud_rejects_conventional_commands_in_pud_states(
    phase_command, conventional_command
):
    dut = make_dut(ramulator.dram.DDR4_PuD)
    addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=80, Column=0)
    dut.issue(phase_command, addr, clk=0)

    with pytest.raises(RuntimeError, match="Invalid bank state"):
        dut.probe(conventional_command, addr, clk=1)


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
