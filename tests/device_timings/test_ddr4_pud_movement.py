import copy

import pytest

import ramulator
from ramulator._ramulator_test import _DeviceUnderTest
import tests.device_timings.harness as device_timings


def make_dram(dram_class=ramulator.dram.DDR4_PuD_Movement, **kwargs):
    return dram_class(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
        **kwargs,
    )


def test_combined_phase3_configuration_preserves_ddr4_pud_baseline():
    baseline = make_dram(ramulator.dram.DDR4_PuD).to_config()
    combined = make_dram().to_config()

    assert combined.pop("impl") == "DDR4_PuD_Movement"
    assert combined.pop("hffs_per_mat") == 4
    baseline.pop("impl")
    baseline_cycles = baseline.pop("command_cycles")
    combined_cycles = combined.pop("command_cycles")
    baseline_timing = baseline.pop("timing")
    combined_timing = combined.pop("timing")
    baseline_constraints = baseline.pop("timing_constraints")
    combined_constraints = combined.pop("timing_constraints")
    assert combined == baseline
    assert combined_timing[:-1] == baseline_timing
    assert combined_timing[-1] == 2
    assert combined_constraints[: len(baseline_constraints)] == baseline_constraints
    assert len(combined_constraints) == len(baseline_constraints) + 6
    assert combined_cycles[: len(baseline_cycles)] == baseline_cycles
    assert combined_cycles[len(baseline_cycles) :] == [1, 1, 1]

    baseline_dut = _DeviceUnderTest(make_dram(ramulator.dram.DDR4_PuD).to_config())
    combined_dut = _DeviceUnderTest(make_dram().to_config())
    assert combined_dut.level_names == baseline_dut.level_names
    assert combined_dut.command_names == [
        *baseline_dut.command_names,
        "ACT_MOV",
        "RD_MOV",
        "WR_MOV",
    ]
    assert combined_dut.state_names == [
        *baseline_dut.state_names,
        "MovementActive",
        "MovementDataValid",
    ]
    assert {
        name: combined_dut.timings[name] for name in baseline_dut.timings
    } == baseline_dut.timings
    assert combined_dut.timings["nRELOC"] == 2
    assert combined_dut.supports_inherited_pud_requests() is True
    assert combined_dut.supports_movement_requests() is False


@pytest.mark.parametrize("command", ("ACT_MOV", "RD_MOV", "WR_MOV"))
def test_movement_command_metadata_and_handlers(command):
    info = _DeviceUnderTest(make_dram().to_config()).command_info(command)
    assert info == {
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


def test_shared_pre_metadata_remains_unchanged():
    baseline = _DeviceUnderTest(make_dram(ramulator.dram.DDR4_PuD).to_config())
    combined = _DeviceUnderTest(make_dram().to_config())

    assert combined.command_info("PREpb") == baseline.command_info("PREpb")


def make_movement_dut():
    return device_timings.DeviceUnderTest(make_dram())


def assert_bank(dut, addr, state):
    assert dut.bank_info(addr) == {"state": state, "row_state": {}}


def test_lc_movement_device_state_trace_and_empty_row_state():
    dut = make_movement_dut()
    source = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=10, Column=3)
    destination = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=20, Column=7)

    assert_bank(dut, source, "Closed")
    dut.issue("ACT_MOV", source, 0)
    assert_bank(dut, source, "MovementActive")
    dut.issue("RD_MOV", source, 1)
    assert_bank(dut, source, "MovementDataValid")
    dut.issue("PREpb", source, 39)
    assert_bank(dut, source, "MovementDataValid")
    dut.issue("ACT_MOV", destination, 55)
    assert_bank(dut, destination, "MovementDataValid")
    dut.issue("WR_MOV", destination, 94)
    assert_bank(dut, destination, "MovementActive")
    dut.issue("PREpb", destination, 95)
    assert_bank(dut, destination, "Closed")


def test_gb_movement_device_state_trace_and_empty_row_state():
    dut = make_movement_dut()
    source = dut.addr_vec(Rank=0, BankGroup=0, Bank=1, Row=30, Column=11)
    destination = dut.addr_vec(Rank=0, BankGroup=0, Bank=1, Row=31, Column=12)

    dut.issue("ACT_MOV", source, 0)
    assert_bank(dut, source, "MovementActive")
    dut.issue("ACT_MOV", destination, 1)
    assert_bank(dut, destination, "MovementActive")
    dut.issue("RD_MOV", source, 2)
    assert_bank(dut, source, "MovementDataValid")
    dut.issue("WR_MOV", destination, 40)
    assert_bank(dut, destination, "MovementActive")
    dut.issue("PREpb", destination, 41)
    assert_bank(dut, destination, "Closed")


def test_act_mov_requests_conventional_precharge_from_opened_bank():
    dut = make_movement_dut()
    opened = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=40, Column=0)
    movement = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=41, Column=0)

    dut.issue("ACT", opened, 0)
    assert dut.probe("ACT_MOV", movement, 1).preq == "PREpb"
    dut.issue("PREpb", movement, dut.timings["nRAS"])
    dut.issue("ACT_MOV", movement, dut.timings["nRAS"] + dut.timings["nRP"])
    assert_bank(dut, movement, "MovementActive")


@pytest.mark.parametrize(
    ("setup_commands", "illegal_command"),
    (
        ((), "RD_MOV"),
        ((), "WR_MOV"),
        (("ACT_MOV",), "WR_MOV"),
        (("ACT_MOV", "RD_MOV"), "RD_MOV"),
    ),
)
def test_malformed_movement_transitions_are_rejected(setup_commands, illegal_command):
    dut = make_movement_dut()
    addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=50, Column=0)
    for clk, command in enumerate(setup_commands):
        dut.issue(command, addr, clk)

    with pytest.raises(RuntimeError, match="Invalid bank state"):
        dut.probe(illegal_command, addr, len(setup_commands))


@pytest.mark.parametrize("pud_command", ("ACT_PUD_OC", "ACT_PUD_S_OC"))
@pytest.mark.parametrize("movement_command", ("ACT_MOV", "RD_MOV", "WR_MOV"))
def test_movement_commands_reject_inherited_pud_intermediate_states(
    pud_command, movement_command
):
    dut = make_movement_dut()
    addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=55, Column=0)
    dut.issue(pud_command, addr, 0)

    with pytest.raises(RuntimeError, match="Invalid bank state"):
        dut.probe(movement_command, addr, 1)


@pytest.mark.parametrize("movement_state", ("MovementActive", "MovementDataValid"))
@pytest.mark.parametrize(
    "command",
    (
        "ACT",
        "RD",
        "WR",
        "RDA",
        "WRA",
        "ACT_PUD",
        "ACT_PUD_OC",
        "ACT_PUD_S",
        "ACT_PUD_S_OC",
        "N",
    ),
)
def test_ordinary_and_inherited_pud_commands_reject_movement_states(movement_state, command):
    dut = make_movement_dut()
    addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=60, Column=0)
    dut.issue("ACT_MOV", addr, 0)
    if movement_state == "MovementDataValid":
        dut.issue("RD_MOV", addr, 1)

    with pytest.raises(RuntimeError, match="Invalid bank state"):
        dut.probe(command, addr, 2)


@pytest.mark.parametrize("maintenance", ("PREab", "REFab"))
@pytest.mark.parametrize("movement_state", ("MovementActive", "MovementDataValid"))
def test_all_bank_maintenance_rejects_movement_without_partial_mutation(
    maintenance, movement_state
):
    dut = make_movement_dut()
    conventional = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=70, Column=0)
    movement = dut.addr_vec(Rank=0, BankGroup=0, Bank=1, Row=80, Column=0)
    all_banks = dut.addr_vec(
        Rank=0,
        BankGroup=dut.ALL,
        Bank=dut.ALL,
        Row=dut.ALL,
        Column=0,
    )

    dut.issue("ACT", conventional, 0)
    dut.issue("ACT_MOV", movement, 1)
    if movement_state == "MovementDataValid":
        dut.issue("RD_MOV", movement, 2)

    with pytest.raises(RuntimeError, match=f"\\[{maintenance}\\] Invalid bank state"):
        dut.probe(maintenance, all_banks, 3)

    assert dut.probe("RD", conventional, dut.timings["nRCD"]).preq == "RD"
    assert_bank(dut, movement, movement_state)


def test_movement_device_timing_constraints_match_accepted_scope():
    inherited_count = len(ramulator.dram.DDR4_PuD.timing_constraints)
    constraints = ramulator.dram.DDR4_PuD_Movement.timing_constraints[inherited_count:]

    assert [
        (tc.level, tc.preceding, tc.following, tc.latency, tc.window, tc.sibling)
        for tc in constraints
    ] == [
        ("Bank", ["ACT_MOV"], ["PREpb", "WR_MOV"], "nRAS", 1, False),
        ("Bank", ["PREpb"], ["ACT_MOV"], "nRP", 1, False),
        ("Rank", ["PREab"], ["ACT_MOV"], "nRP", 1, False),
        ("Bank", ["RDA"], ["ACT_MOV"], "nRTP + nRP", 1, False),
        (
            "Bank",
            ["WRA"],
            ["ACT_MOV"],
            "nCWL + nBL + nWR + nRP",
            1,
            False,
        ),
        ("Rank", ["REFab"], ["ACT_MOV"], "nRFC", 1, False),
    ]


def test_latest_act_mov_controls_precharge_and_write_boundaries():
    pre_dut = make_movement_dut()
    addr = pre_dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=90, Column=0)
    pre_dut.issue("ACT_MOV", addr, 0)
    pre_dut.issue("ACT_MOV", addr, 1)
    pre_dut.assert_earliest_ready_at("PREpb", addr, 1 + pre_dut.timings["nRAS"])

    write_dut = make_movement_dut()
    addr = write_dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=91, Column=0)
    write_dut.issue("ACT_MOV", addr, 0)
    write_dut.issue("ACT_MOV", addr, 1)
    write_dut.issue("RD_MOV", addr, 2)
    write_dut.assert_earliest_ready_at("WR_MOV", addr, 1 + write_dut.timings["nRAS"])


def test_successive_gb_activations_have_no_device_row_cycle_edge():
    dut = make_movement_dut()
    addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=100, Column=0)

    dut.issue("ACT_MOV", addr, 0)
    assert dut.probe("ACT_MOV", addr, 1).ready is True


@pytest.mark.parametrize("preceding_command", ("PREpb", "PREab", "RDA", "WRA", "REFab"))
def test_act_mov_inherits_conventional_recovery_boundaries(preceding_command):
    dut = make_movement_dut()
    addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=110, Column=0)

    if preceding_command == "REFab":
        all_banks = dut.addr_vec(
            Rank=0, BankGroup=dut.ALL, Bank=dut.ALL, Row=dut.ALL, Column=0
        )
        dut.issue("REFab", all_banks, 0)
        expected = dut.timings["nRFC"]
    else:
        dut.issue("ACT", addr, 0)
        preceding_clk = (
            dut.timings["nRCD"] if preceding_command in ("RDA", "WRA") else dut.timings["nRAS"]
        )
        dut.issue(preceding_command, addr, preceding_clk)
        recovery = {
            "PREpb": dut.timings["nRP"],
            "PREab": dut.timings["nRP"],
            "RDA": dut.timings["nRTP"] + dut.timings["nRP"],
            "WRA": dut.timings["nCWL"]
            + dut.timings["nBL"]
            + dut.timings["nWR"]
            + dut.timings["nRP"],
        }[preceding_command]
        expected = preceding_clk + recovery

    dut.assert_earliest_ready_at("ACT_MOV", addr, expected)


@pytest.mark.parametrize(
    "following_command", ("ACT", "ACT_PUD_OC", "ACT_PUD_S_OC", "ACT_MOV", "REFab")
)
def test_terminal_movement_precharge_preserves_recovery(following_command):
    dut = make_movement_dut()
    addr = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=120, Column=0)
    all_banks = dut.addr_vec(
        Rank=0, BankGroup=dut.ALL, Bank=dut.ALL, Row=dut.ALL, Column=0
    )

    dut.issue("ACT_MOV", addr, 0)
    terminal_pre = dut.timings["nRAS"]
    dut.issue("PREpb", addr, terminal_pre)
    following_addr = all_banks if following_command == "REFab" else addr
    dut.assert_earliest_ready_at(
        following_command, following_addr, terminal_pre + dut.timings["nRP"]
    )


def test_latest_act_mov_timing_is_bank_local():
    dut = make_movement_dut()
    peer = dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=130, Column=0)
    later_other_bank = dut.addr_vec(
        Rank=0, BankGroup=0, Bank=1, Row=131, Column=0
    )

    dut.issue("ACT_MOV", peer, 0)
    dut.issue("RD_MOV", peer, 1)
    dut.issue("ACT_MOV", later_other_bank, 2)
    dut.assert_earliest_ready_at("WR_MOV", peer, dut.timings["nRAS"])


def test_movement_commands_are_excluded_from_activation_current_and_dq_groups():
    constraints = ramulator.dram.DDR4_PuD_Movement.timing_constraints

    activation_current = [
        tc
        for tc in constraints
        if tc.level in ("Rank", "BankGroup") and tc.latency in ("nRRDS", "nRRDL", "nFAW")
    ]
    dq_constraints = [
        tc
        for tc in constraints
        if tc.level in ("Channel", "Rank", "BankGroup")
        and any(command in ("RD_MOV", "WR_MOV") for command in tc.preceding + tc.following)
    ]

    assert all("ACT_MOV" not in tc.preceding + tc.following for tc in activation_current)
    assert dq_constraints == []


def test_combined_mutable_definitions_are_independent_from_both_bases():
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
        combined = getattr(ramulator.dram.DDR4_PuD_Movement, name)
        assert combined is not getattr(ramulator.dram.DDR4_PuD, name)
        assert combined is not getattr(ramulator.dram.DDR4, name)

    assert all(
        combined_tc is not baseline_tc
        for combined_tc, baseline_tc in zip(
            ramulator.dram.DDR4_PuD_Movement.timing_constraints,
            ramulator.dram.DDR4_PuD.timing_constraints,
        )
    )

    definitions = copy.deepcopy(ramulator.dram.DDR4_PuD_Movement.commands)
    ramulator.dram.DDR4_PuD_Movement.commands.append("TEST_ONLY")
    try:
        assert "TEST_ONLY" not in ramulator.dram.DDR4_PuD.commands
        assert "TEST_ONLY" not in ramulator.dram.DDR4.commands
    finally:
        ramulator.dram.DDR4_PuD_Movement.commands = definitions


def test_hffs_per_mat_default_and_positive_override_reach_device():
    default_dut = _DeviceUnderTest(make_dram().to_config())
    override_dut = _DeviceUnderTest(make_dram(hffs_per_mat=8).to_config())

    assert default_dut.supports_hffs_per_mat_config is True
    assert default_dut.hffs_per_mat == 4
    assert override_dut.hffs_per_mat == 8


@pytest.mark.parametrize("value", (0, -1))
def test_hffs_per_mat_rejects_non_positive_values(value):
    with pytest.raises(ValueError, match="hffs_per_mat must be positive"):
        make_dram(hffs_per_mat=value)

    config = make_dram().to_config()
    config["hffs_per_mat"] = value
    with pytest.raises(RuntimeError, match="hffs_per_mat must be positive"):
        _DeviceUnderTest(config)


def test_hffs_per_mat_rejects_non_integer_values():
    with pytest.raises(TypeError, match="hffs_per_mat must be an int"):
        make_dram(hffs_per_mat=4.0)


@pytest.mark.parametrize("dram_class", (ramulator.dram.DDR4, ramulator.dram.DDR4_PuD))
def test_hffs_per_mat_is_absent_and_unsupported_on_existing_standards(dram_class):
    config = make_dram(dram_class).to_config()
    assert "hffs_per_mat" not in config

    dut = _DeviceUnderTest(config)
    assert dut.supports_hffs_per_mat_config is False
    assert dut.hffs_per_mat == -1

    config["hffs_per_mat"] = 4
    with pytest.raises(RuntimeError, match="hffs_per_mat is unsupported"):
        _DeviceUnderTest(config)
