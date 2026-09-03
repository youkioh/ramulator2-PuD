import pytest

import ramulator
import tests.controller_scheduling.harness as cs


pytestmark = pytest.mark.controller_scheduling


def make_movement_dut(*, scheduler=None):
    dram = ramulator.dram.DDR4_PuD_Movement(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    return cs.ControllerUnderTest.make_generic_ddr(
        dram,
        scheduler=scheduler,
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
        row_policy=ramulator.row_policy.Open(),
    )


def operand(dut, *, bank=0, row=0, column=0):
    return dut.addr_vec(
        Rank=0,
        BankGroup=0,
        Bank=bank,
        Row=row,
        Column=column,
    )


def movement_operands(dut, *, bank=0):
    return [
        operand(dut, bank=bank, row=100, column=3),
        operand(dut, bank=bank, row=101, column=5),
    ]


def advance_empty_to(dut, clk):
    for _ in range(clk):
        assert dut.tick() == []


@pytest.mark.parametrize(
    ("type_name", "occurrence_index", "history", "ready_clk"),
    [
        ("LC-MOV", 1, [0, -1, -1, -1, -1, -1], 16),
        ("LC-MOV", 2, [0, 10, -1, -1, -1, -1], 19),
        ("LC-MOV", 5, [0, 1, 2, 3, 10, -1], 30),
        ("GB-MOV", 2, [0, 1, -1, -1, -1], 39),
        ("GB-MOV", 3, [0, 1, 10, -1, -1], 12),
        ("GB-MOV", 4, [0, 1, 2, 10, -1], 28),
    ],
)
def test_each_primitive_local_edge_is_tight_and_independent_of_device_timing(
    type_name, occurrence_index, history, ready_clk
):
    dut = make_movement_dut()
    operands = movement_operands(dut)
    advance_empty_to(dut, ready_clk - 1)

    early = dut.probe_movement_timing(
        type_name, operands, occurrence_index, history
    )
    assert early["local_ready"] is False
    assert early["device_ready"] is True
    assert early["request_ready"] is False

    assert dut.tick() == []
    ontime = dut.probe_movement_timing(
        type_name, operands, occurrence_index, history
    )
    assert ontime["local_ready"] is True
    assert ontime["device_ready"] is True
    assert ontime["request_ready"] is True


def test_gb_read_uses_source_act_occurrence_zero_not_latest_act():
    dut = make_movement_dut()
    operands = movement_operands(dut)
    advance_empty_to(dut, 39)

    probe = dut.probe_movement_timing(
        "GB-MOV", operands, 2, [0, 10, -1, -1, -1]
    )

    assert probe["local_ready"] is True
    assert probe["request_ready"] is True


@pytest.mark.parametrize(
    ("type_name", "occurrence_index", "history"),
    [
        ("LC-MOV", 0, [-1, -1, -1, -1, -1, -1]),
        ("LC-MOV", 3, [0, 1, 2, -1, -1, -1]),
        ("GB-MOV", 0, [-1, -1, -1, -1, -1]),
        ("GB-MOV", 1, [0, -1, -1, -1, -1]),
    ],
)
def test_occurrences_without_accepted_local_edges_add_no_local_constraint(
    type_name, occurrence_index, history
):
    dut = make_movement_dut()

    probe = dut.probe_movement_timing(
        type_name, movement_operands(dut), occurrence_index, history
    )

    assert probe["local_ready"] is True
    assert probe["request_ready"] == probe["device_ready"]


def test_composite_readiness_also_preserves_a_device_only_block():
    dut = make_movement_dut()
    operands = movement_operands(dut)
    dut.send_movement_request_for_testing("LC-MOV", operands, 0, 0)
    assert [item.command for item in dut.tick()] == ["ACT_MOV"]
    for _ in range(15):
        assert dut.tick() == []
    assert [item.command for item in dut.tick()] == ["RD_MOV"]
    for _ in range(3):
        assert dut.tick() == []

    probe = dut.probe_movement_timing(
        "LC-MOV", operands, 5, [0, 0, 0, 0, 0, -1]
    )

    assert probe["clk"] == 20
    assert probe["local_ready"] is True
    assert probe["device_ready"] is False
    assert probe["request_ready"] is False
    dut.run_until_idle(max_ticks=160)


@pytest.mark.parametrize(
    ("type_name", "second_mat", "commands", "issue_clks", "depart"),
    [
        (
            "LC-MOV",
            0,
            ["ACT_MOV", "RD_MOV", "PREpb", "ACT_MOV", "WR_MOV", "PREpb"],
            [0, 16, 39, 55, 94, 114],
            130,
        ),
        (
            "GB-MOV",
            1,
            ["ACT_MOV", "ACT_MOV", "RD_MOV", "WR_MOV", "PREpb"],
            [0, 1, 39, 41, 59],
            75,
        ),
    ],
)
@pytest.mark.parametrize(
    "scheduler_factory",
    [ramulator.scheduler.FRFCFS, ramulator.scheduler.FRFCFSRowHit],
)
def test_schedulers_enforce_exact_isolated_movement_cycles(
    type_name, second_mat, commands, issue_clks, depart, scheduler_factory
):
    dut = make_movement_dut(scheduler=scheduler_factory())
    dut.send_movement_request_for_testing(
        type_name, movement_operands(dut), 0, second_mat
    )

    history = dut.run_until_idle(max_ticks=160)

    assert [item.command for item in history] == commands
    first_issue = history[0].clk
    assert [item.clk - first_issue for item in history] == issue_clks
    assert dut.completions()[0]["depart"] - first_issue == depart


def test_combined_standard_has_no_movement_timing_aliases():
    dut = make_movement_dut()

    assert [name for name in dut.command_names if "MOV" in name] == [
        "ACT_MOV",
        "RD_MOV",
        "WR_MOV",
    ]


@pytest.mark.parametrize("traffic", ["Read", "Write", "NOT"])
def test_ready_different_bank_work_beats_older_locally_blocked_movement(traffic):
    dut = make_movement_dut()
    dut.send_movement_request_for_testing(
        "LC-MOV", movement_operands(dut, bank=0), 0, 0, source_id=1
    )
    assert [(item.command, item.source_id) for item in dut.tick()] == [
        ("ACT_MOV", 1)
    ]

    other = operand(dut, bank=1, row=200)
    if traffic == "NOT":
        dut.send_pud_request("NOT", [other], source_id=2)
    else:
        dut.send_request(traffic, other, source_id=2)

    assert [(item.command, item.source_id) for item in dut.tick()] == [
        ("ACT_PUD_S_OC" if traffic == "NOT" else "ACT", 2)
    ]
    dut.run_until_idle(max_ticks=256)


def test_staged_post_selection_command_is_rejected_by_final_validation():
    dram = ramulator.dram.DDR4(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    dut = cs.ControllerUnderTest.make_generic_ddr(
        dram,
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
        row_policy=ramulator.row_policy.Open(),
    )
    addr = operand(dut, row=300)
    dut.priority_send("ACT", addr)
    assert [item.command for item in dut.tick()] == ["ACT"]
    for _ in range(dut.timings["nRCD"]):
        assert dut.tick() == []

    history_before = list(dut.history)
    assert dut.probe_final_issue_validation("Read", "RD", "RD", addr) is True
    assert (
        dut.probe_final_issue_validation("Read", "PREpb", "RD", addr) is False
    )
    assert dut.history == history_before


@pytest.mark.parametrize(
    (
        "protected_type",
        "candidate_type",
        "candidate_command",
        "protected_close",
        "mutated_close",
    ),
    [
        ("Write", "Read", "RD", "WRA", "RDA"),
        ("Read", "Write", "WR", "RDA", "WRA"),
    ],
)
def test_final_validation_rechecks_active_close_protection_after_closedcap_upgrade(
    protected_type,
    candidate_type,
    candidate_command,
    protected_close,
    mutated_close,
):
    dram = ramulator.dram.DDR4(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    dut = cs.ControllerUnderTest.make_generic_ddr(
        dram,
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
        row_policy=ramulator.row_policy.ClosedCAP(cap=1),
    )
    other_bank = operand(dut, bank=1, row=10)
    protected_bank = operand(dut, bank=0, row=20)

    # Keep another Bank open so its column command can create a turnaround
    # gap after the protected request acquires the active slot.
    dut.priority_send("ACT", other_bank)
    assert [item.command for item in dut.tick()] == ["ACT"]
    for _ in range(dut.timings["nRCD"]):
        assert dut.tick() == []

    dut.send_request(protected_type, protected_bank, source_id=1)
    assert [(item.command, item.source_id) for item in dut.tick()] == [
        ("ACT", 1)
    ]
    for _ in range(dut.timings["nRCD"] - 2):
        assert dut.tick() == []

    dut.send_request(candidate_type, other_bank, source_id=2)
    dut.send_request(candidate_type, protected_bank, source_id=3)
    dut.send_request(
        candidate_type,
        operand(dut, bank=0, row=20, column=8),
        source_id=4,
    )

    first_same_bank = None
    for _ in range(2 * dut.timings["nCCDL"]):
        issued = dut.tick()
        first_same_bank = next(
            (item for item in issued if item.source_id == 3), first_same_bank
        )
        if first_same_bank is not None:
            break
    assert first_same_bank is not None
    assert first_same_bank.command == candidate_command

    # At the next same-Bank CAS boundary, source 4 is selected and ClosedCAP
    # upgrades it to a closing command. The active source-1 request still
    # protects the Bank, so final validation must reject the mutated issue.
    for _ in range(dut.timings["nCCDL"] - 1):
        assert not any(item.source_id == 4 for item in dut.tick())
    assert dut.tick() == []

    dut.run_until_idle(max_ticks=256)
    protected_final_index = next(
        index
        for index, item in enumerate(dut.history)
        if item.source_id == 1 and item.command == protected_close
    )
    mutated_close_index = next(
        index
        for index, item in enumerate(dut.history)
        if item.source_id == 4 and item.command == mutated_close
    )

    assert protected_final_index < mutated_close_index
    assert [
        (item.command, item.source_id)
        for item in dut.history
        if item.addr_vec[dut.level_names.index("Bank")] == 0
    ][:3] == [
        ("ACT", 1),
        (candidate_command, 3),
        (protected_close, 1),
    ]
    assert dut.is_idle()


def test_local_readiness_probe_is_pure_and_reserves_no_other_bank_resource():
    dut = make_movement_dut()
    operands = movement_operands(dut)
    advance_empty_to(dut, 15)

    probe = dut.probe_movement_timing(
        "LC-MOV", operands, 1, [0, -1, -1, -1, -1, -1]
    )
    assert probe["request_ready"] is False
    assert probe["cursor_before"] == probe["cursor_after"] == 1
    assert probe["history_before"] == probe["history_after"]

    dut.send_request("Read", operand(dut, bank=1, row=200), source_id=2)
    assert [(item.command, item.source_id) for item in dut.tick()] == [("ACT", 2)]
    dut.run_until_idle(max_ticks=128)


@pytest.mark.parametrize("standard", ["DDR4", "DDR4_PuD", "movement"])
def test_generic_ddr_nonmovement_request_readiness_is_exactly_device_timing(
    standard,
):
    dram_class = {
        "DDR4": ramulator.dram.DDR4,
        "DDR4_PuD": ramulator.dram.DDR4_PuD,
        "movement": ramulator.dram.DDR4_PuD_Movement,
    }[standard]
    dram = dram_class(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    dut = cs.ControllerUnderTest.make_generic_ddr(dram)
    addr = operand(dut, row=300)
    dut.send_request("Read", addr)
    assert [item.command for item in dut.tick()] == ["ACT"]

    probe = dut.probe_command_timing("Read", "RD", addr)

    assert probe["device_ready"] is False
    assert probe["request_ready"] == probe["device_ready"]


def test_non_generic_controller_request_readiness_defaults_to_device_timing():
    dram = ramulator.dram.GDDR7(
        org_preset="GDDR7_16Gb_x8",
        timing_preset="GDDR7_28000_PAM3",
    )
    dut = cs.ControllerUnderTest.make_gddr7(
        dram,
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
    )
    addr = dut.addr_vec(Channel=0, Bank=0, Row=0, Column=0)

    probe = dut.probe_command_timing("Read", "ACT", addr)

    assert probe["device_ready"] is True
    assert probe["request_ready"] == probe["device_ready"]
