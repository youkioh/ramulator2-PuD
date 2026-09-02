import pytest
from ramulator._ramulator_test import _DeviceUnderTest
from ramulator.dram.spec import CONTROLLER_SEQUENCED

import ramulator
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
    assert pud.command_names[: len(ddr4.command_names)] == ddr4.command_names
    assert {name: pud.timings[name] for name in ddr4.timings} == ddr4.timings

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


@pytest.mark.parametrize("opening_command", ("ACT_PUD_OC", "ACT_PUD_S_OC"))
def test_ddr4_pud_opening_requests_prepb_from_conventional_opened(opening_command):
    dut = make_dut(ramulator.dram.DDR4_PuD)
    addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=9, Column=0)

    dut.issue("ACT", addr, clk=0)

    assert dut.probe(opening_command, addr, clk=0).preq == "PREpb"


def test_ddr4_pud_rowcopy_device_transitions_support_repeated_destinations():
    dut = make_dut(ramulator.dram.DDR4_PuD)
    source = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=0)
    destinations = [
        dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=row, Column=0) for row in (20, 21, 22)
    ]

    dut.issue("ACT_PUD_S_OC", source, clk=0)
    for clk, destination in zip((40, 45, 50), destinations):
        assert dut.probe("ACT_PUD", destination, clk=clk).ready is True
        dut.issue("ACT_PUD", destination, clk=clk)

    assert dut.probe("N", destinations[-1], clk=55).ready is True
    dut.issue("PREpb", destinations[-1], clk=55)
    assert dut.probe("RD", source, clk=56).preq == "ACT"


@pytest.mark.parametrize("additional_activations", (1, 3))
def test_ddr4_pud_majority_device_transitions(additional_activations):
    dut = make_dut(ramulator.dram.DDR4_PuD)
    rows = [
        dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=row, Column=0)
        for row in range(30, 32 + additional_activations)
    ]

    dut.issue("ACT_PUD_OC", rows[0], clk=0)
    activation_clks = range(11, 11 + 5 * additional_activations, 5)
    for clk, row in zip(activation_clks, rows[1:-1]):
        dut.issue("ACT_PUD", row, clk=clk)
    sensed_clk = 11 + 5 * additional_activations
    dut.issue("ACT_PUD_S", rows[-1], clk=sensed_clk)
    precharge_clk = sensed_clk + 34
    dut.issue("PREpb", rows[-1], clk=precharge_clk)

    assert dut.probe("ACT_PUD_OC", rows[0], clk=precharge_clk + 16).ready is True


def test_ddr4_pud_not_device_transitions():
    dut = make_dut(ramulator.dram.DDR4_PuD)
    source = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=40, Column=0)

    dut.issue("ACT_PUD_S_OC", source, clk=0)
    dut.issue("N", source, clk=40)
    assert dut.probe("ACT_PUD", source, clk=83).ready is True
    dut.issue("PREpb", source, clk=83)

    assert dut.probe("ACT_PUD_S_OC", source, clk=99).ready is True


def test_ddr4_pud_gate8_timing_parameters_and_command_cycles():
    dram = ramulator.dram.DDR4_PuD(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    config = dram.to_config()
    _, timings = dram.resolve()

    assert timings["tCK_ps"] == 833
    assert timings["nRP"] == 16
    assert {
        name: timings[name]
        for name in (
            "nPUD_ACT_OC",
            "nPUD_ACT",
            "nPUD_ACT_S_OC",
            "nPUD_ACT_S",
            "nPUD_N",
        )
    } == {
        "nPUD_ACT_OC": 11,
        "nPUD_ACT": 5,
        "nPUD_ACT_S_OC": 40,
        "nPUD_ACT_S": 34,
        "nPUD_N": 43,
    }
    command_cycles = dict(zip(dram.commands, config["command_cycles"]))
    for command in ("ACT_PUD", "ACT_PUD_OC", "ACT_PUD_S", "ACT_PUD_S_OC", "N"):
        assert command_cycles[command] == 1


@pytest.mark.parametrize(
    ("destination_count", "expected_total"),
    ((1, 61), (8, 96)),
)
def test_ddr4_pud_rowcopy_timing_boundaries_scale_linearly(destination_count, expected_total):
    dut = make_dut(ramulator.dram.DDR4_PuD)
    source = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=100, Column=0)
    destinations = [
        dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=101 + i, Column=0)
        for i in range(destination_count)
    ]

    dut.issue("ACT_PUD_S_OC", source, clk=0)
    clk = 40
    for destination in destinations:
        dut.assert_earliest_ready_at("ACT_PUD", destination, clk)
        dut.issue("ACT_PUD", destination, clk)
        clk += 5
    dut.assert_earliest_ready_at("PREpb", destinations[-1], clk)
    dut.issue("PREpb", destinations[-1], clk)
    dut.assert_earliest_ready_at("ACT_PUD_S_OC", source, expected_total)


@pytest.mark.parametrize(
    ("additional_activations", "expected_total"),
    ((1, 66), (3, 76)),
)
def test_ddr4_pud_majority_timing_boundaries(additional_activations, expected_total):
    dut = make_dut(ramulator.dram.DDR4_PuD)
    rows = [
        dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=120 + i, Column=0)
        for i in range(additional_activations + 2)
    ]

    dut.issue("ACT_PUD_OC", rows[0], clk=0)
    clk = 11
    for row in rows[1:-1]:
        dut.assert_earliest_ready_at("ACT_PUD", row, clk)
        dut.issue("ACT_PUD", row, clk)
        clk += 5
    dut.assert_earliest_ready_at("ACT_PUD_S", rows[-1], clk)
    dut.issue("ACT_PUD_S", rows[-1], clk)
    clk += 34
    dut.assert_earliest_ready_at("PREpb", rows[-1], clk)
    dut.issue("PREpb", rows[-1], clk)
    dut.assert_earliest_ready_at("ACT_PUD_OC", rows[0], expected_total)


def test_ddr4_pud_not_uses_aggregate_n_timing_boundaries():
    dut = make_dut(ramulator.dram.DDR4_PuD)
    source = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=140, Column=0)

    dut.issue("ACT_PUD_S_OC", source, clk=0)
    dut.assert_earliest_ready_at("N", source, 40)
    dut.issue("N", source, clk=40)
    dut.assert_earliest_ready_at("PREpb", source, 83)
    dut.issue("PREpb", source, clk=83)
    dut.assert_earliest_ready_at("ACT_PUD_S_OC", source, 99)


@pytest.mark.parametrize("opening_command", ("ACT_PUD_OC", "ACT_PUD_S_OC"))
@pytest.mark.parametrize("preceding_command", ("PREpb", "PREab", "RDA", "WRA", "REFab"))
def test_ddr4_pud_opening_inherits_conventional_recovery_boundaries(
    preceding_command, opening_command
):
    dut = make_dut(ramulator.dram.DDR4_PuD)
    addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=160, Column=0)

    if preceding_command == "REFab":
        ref_addr = dut.addr_vec(Rank=0, BankGroup=dut.ALL, Bank=dut.ALL, Row=dut.ALL, Column=0)
        dut.issue("REFab", ref_addr, clk=0)
        expected = dut.timings["nRFC"]
    else:
        dut.issue("ACT", addr, clk=0)
        if preceding_command in ("RDA", "WRA"):
            preceding_clk = dut.timings["nRCD"]
        else:
            preceding_clk = dut.timings["nRAS"]
        dut.issue(preceding_command, addr, clk=preceding_clk)
        recovery = {
            "PREpb": dut.timings["nRP"],
            "PREab": dut.timings["nRP"],
            "RDA": dut.timings["nRTP"] + dut.timings["nRP"],
            "WRA": (
                dut.timings["nCWL"] + dut.timings["nBL"] + dut.timings["nWR"] + dut.timings["nRP"]
            ),
        }[preceding_command]
        expected = preceding_clk + recovery

    dut.assert_earliest_ready_at(opening_command, addr, expected)


def test_ddr4_pud_final_precharge_uses_ordinary_act_recovery():
    dut = make_dut(ramulator.dram.DDR4_PuD)
    source = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=180, Column=0)
    destination = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=181, Column=0)

    dut.issue("ACT_PUD_S_OC", source, clk=0)
    dut.issue("ACT_PUD", destination, clk=40)
    dut.issue("PREpb", destination, clk=45)
    dut.assert_earliest_ready_at("ACT", source, 61)


@pytest.mark.parametrize("peer_rank", (0, 1))
def test_ddr4_pud_timing_is_bank_local(peer_rank):
    dram = ramulator.dram.DDR4_PuD(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=2,
    )
    dut = device_timings.DeviceUnderTest(dram)
    source = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=200, Column=0)
    peer = dut.addr_vec(
        Rank=peer_rank,
        BankGroup=1 if peer_rank == 0 else 0,
        Bank=0,
        Row=201,
        Column=0,
    )

    dut.issue("ACT_PUD_S_OC", source, clk=0)
    assert dut.probe("ACT_PUD_S_OC", peer, clk=1).ready is True


def test_ddr4_pud_activations_do_not_participate_in_nrrd_or_nfaw():
    pud_then_act = make_dut(ramulator.dram.DDR4_PuD)
    banks = [
        pud_then_act.addr_vec(Rank=0, BankGroup=i, Bank=0, Row=220 + i, Column=0) for i in range(4)
    ] + [pud_then_act.addr_vec(Rank=0, BankGroup=0, Bank=1, Row=224, Column=0)]
    for clk, addr in enumerate(banks[:4]):
        pud_then_act.issue("ACT_PUD_S_OC", addr, clk=clk)
    assert pud_then_act.probe("ACT", banks[4], clk=4).ready is True

    act_then_pud = make_dut(ramulator.dram.DDR4_PuD)
    for index, addr in enumerate(banks[:4]):
        act_then_pud.issue("ACT", addr, clk=index * 6)
    assert act_then_pud.probe("ACT_PUD_S_OC", banks[4], clk=19).ready is True


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
def test_ddr4_pud_rejects_conventional_commands_in_pud_states(phase_command, conventional_command):
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
