import pytest

import ramulator
import tests.controller_scheduling.harness as cs


pytestmark = pytest.mark.controller_scheduling


def make_dut(*, scheduler=None):
    dram = ramulator.dram.DDR4_PuD_Movement(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    return cs.ControllerUnderTest.make_generic_ddr(
        dram,
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
        row_policy=ramulator.row_policy.Open(),
        scheduler=scheduler,
        num_cores=8,
    )


def operand(dut, *, bank=0, row=0, column=0):
    return dut.addr_vec(
        Rank=0,
        BankGroup=0,
        Bank=bank,
        Row=row,
        Column=column,
    )


def send_lc(dut, *, bank=0, source_row=0, destination_row=1, source_id=1):
    dut.send_movement_request_for_testing(
        "LC-MOV",
        [
            operand(dut, bank=bank, row=source_row, column=3),
            operand(dut, bank=bank, row=destination_row, column=5),
        ],
        0,
        0,
        source_id,
    )


def send_gb(dut, *, bank=0, source_row=0, destination_row=1, source_id=1):
    dut.send_movement_request_for_testing(
        "GB-MOV",
        [
            operand(dut, bank=bank, row=source_row, column=3),
            operand(dut, bank=bank, row=destination_row, column=5),
        ],
        0,
        1,
        source_id,
    )


def tick_until(dut, predicate, max_ticks=256):
    for _ in range(max_ticks):
        issued = dut.tick()
        match = next((item for item in issued if predicate(item)), None)
        if match is not None:
            return match
    raise AssertionError("Expected command did not issue")


def terminal_pre(dut, source_id=1):
    pres = [
        item
        for item in dut.history
        if item.source_id == source_id and item.command == "PREpb"
    ]
    return pres[1] if len(pres) >= 2 else None


def test_pending_movement_owns_nothing_and_fifo_priority_head_wins():
    dut = make_dut()
    bank = operand(dut, bank=0, row=10)
    send_lc(dut, bank=0, source_row=11, destination_row=12)
    dut.priority_send("PREpb", bank)

    issued = dut.tick()

    assert [(item.command, item.source_id) for item in issued] == [("PREpb", -2)]
    assert not any(item.command == "ACT_MOV" for item in dut.history)


def test_preparatory_precharge_owns_nothing_and_reopened_bank_is_precharged_again():
    dut = make_dut()
    opened = operand(dut, bank=0, row=20)
    dut.send_request("Read", opened, source_id=7)
    dut.run_until_idle(max_ticks=128)

    send_lc(dut, bank=0, source_row=21, destination_row=22)
    first_prep = tick_until(
        dut, lambda item: item.source_id == 1 and item.command == "PREpb"
    )
    assert not any(item.command == "ACT_MOV" for item in dut.history)

    dut.priority_send("ACT", operand(dut, bank=0, row=23))
    reopened = tick_until(
        dut, lambda item: item.source_id == -2 and item.command == "ACT"
    )
    second_prep = tick_until(
        dut,
        lambda item: item.source_id == 1
        and item.command == "PREpb"
        and item.clk > first_prep.clk,
    )
    first_movement_act = tick_until(
        dut, lambda item: item.source_id == 1 and item.command == "ACT_MOV"
    )

    assert first_prep.clk < reopened.clk < second_prep.clk < first_movement_act.clk


@pytest.mark.parametrize(
    "interrupter",
    [
        "read",
        "write",
        "inherited_pud",
        "movement",
        "priority_single",
        "priority_all",
        "refresh_all",
    ],
)
def test_first_act_acquires_owner_and_blocks_each_same_bank_interrupter(interrupter):
    dut = make_dut()
    send_lc(dut, bank=0, source_row=30, destination_row=31)
    first = dut.tick()
    assert [(item.command, item.source_id) for item in first] == [("ACT_MOV", 1)]

    if interrupter == "read":
        dut.send_request("Read", operand(dut, bank=0, row=32), source_id=2)
    elif interrupter == "write":
        dut.send_request("Write", operand(dut, bank=0, row=32), source_id=2)
    elif interrupter == "inherited_pud":
        dut.send_pud_request("NOT", [operand(dut, bank=0, row=32)], source_id=2)
    elif interrupter == "movement":
        send_lc(dut, bank=0, source_row=32, destination_row=33, source_id=2)
    elif interrupter == "priority_single":
        dut.priority_send("PREpb", operand(dut, bank=0, row=32))
    elif interrupter == "priority_all":
        dut.priority_send("PREab", operand(dut, bank=0, row=32))
    else:
        dut.priority_send("REFab", operand(dut, bank=0, row=32))

    final_pre = tick_until(dut, lambda item: terminal_pre(dut) is item)
    before_release = [item for item in dut.history if item.clk <= final_pre.clk]
    assert all(item.source_id == 1 for item in before_release)

    released_work = tick_until(dut, lambda item: item.source_id != 1)
    assert released_work.clk > final_pre.clk


def test_gb_owner_is_acquired_by_source_act_and_released_by_terminal_pre():
    dut = make_dut()
    send_gb(dut, bank=0, source_row=34, destination_row=35)
    assert [(item.command, item.source_id) for item in dut.tick()] == [
        ("ACT_MOV", 1)
    ]

    dut.send_request("Read", operand(dut, bank=0, row=36), source_id=2)
    final_pre = tick_until(
        dut,
        lambda item: item.source_id == 1 and item.command == "PREpb",
    )
    assert all(item.source_id == 1 for item in dut.history)

    released = tick_until(dut, lambda item: item.source_id == 2)
    assert released.clk > final_pre.clk


def test_different_bank_read_progresses_while_owner_is_timing_blocked():
    dut = make_dut()
    send_lc(dut, bank=0, source_row=40, destination_row=41)
    assert [item.command for item in dut.tick()] == ["ACT_MOV"]

    dut.send_request("Read", operand(dut, bank=1, row=42), source_id=2)
    other_read = tick_until(
        dut, lambda item: item.source_id == 2 and item.command == "RD"
    )
    owner_source_pre = tick_until(
        dut, lambda item: item.source_id == 1 and item.command == "PREpb"
    )

    assert other_read.clk < owner_source_pre.clk


def test_different_banks_can_hold_independent_movement_owners():
    dut = make_dut()
    send_lc(dut, bank=0, source_row=50, destination_row=51, source_id=1)
    send_lc(dut, bank=1, source_row=52, destination_row=53, source_id=2)

    for _ in range(18):
        dut.tick()

    assert [
        (item.command, item.source_id)
        for item in dut.history
        if item.command in ("ACT_MOV", "RD_MOV")
    ] == [
        ("ACT_MOV", 1),
        ("ACT_MOV", 2),
        ("RD_MOV", 1),
        ("RD_MOV", 2),
    ]


def test_rowhit_scheduler_applies_ownership_before_prerequisite_resolution():
    dut = make_dut(scheduler=ramulator.scheduler.FRFCFSRowHit())
    send_lc(dut, bank=0, source_row=54, destination_row=55)
    assert [item.command for item in dut.tick()] == ["ACT_MOV"]

    dut.send_request("Read", operand(dut, bank=0, row=56), source_id=2)
    dut.send_request("Read", operand(dut, bank=1, row=57), source_id=3)
    other_bank = tick_until(dut, lambda item: item.source_id == 3)
    owner_source_pre = tick_until(
        dut, lambda item: item.source_id == 1 and item.command == "PREpb"
    )

    assert other_bank.clk < owner_source_pre.clk
    assert not any(item.source_id == 2 for item in dut.history)


def test_blocked_all_bank_priority_head_prevents_different_bank_bypass():
    dut = make_dut()
    send_lc(dut, bank=0, source_row=60, destination_row=61)
    assert [item.command for item in dut.tick()] == ["ACT_MOV"]

    dut.priority_send("PREab", operand(dut, bank=0, row=62))
    dut.send_request("Read", operand(dut, bank=1, row=63), source_id=2)
    assert dut.tick() == []

    final_pre = tick_until(dut, lambda item: terminal_pre(dut) is item)
    priority = tick_until(
        dut, lambda item: item.source_id == -2 and item.command == "PREab"
    )
    other = tick_until(dut, lambda item: item.source_id == 2)

    assert final_pre.clk < priority.clk < other.clk


@pytest.mark.parametrize(
    ("older", "expected_source"),
    [("movement", 1), ("read", 2)],
)
def test_oldest_ready_pending_movement_and_read_keep_existing_age_order(
    older, expected_source
):
    dut = make_dut()
    bank = operand(dut, bank=1, row=70)
    if older == "movement":
        send_lc(dut, bank=0, source_row=71, destination_row=72, source_id=1)
    else:
        dut.send_request("Read", bank, source_id=2)

    dut.priority_send("PREab", operand(dut, bank=0, row=73))
    assert [item.command for item in dut.tick()] == ["PREab"]

    if older == "movement":
        dut.send_request("Read", bank, source_id=2)
    else:
        send_lc(dut, bank=0, source_row=71, destination_row=72, source_id=1)

    selected = tick_until(dut, lambda item: item.command != "PREab")
    assert selected.source_id == expected_source


def test_equal_arrival_keeps_deterministic_pud_tie_break_for_movement():
    dut = make_dut()
    dut.send_request("Read", operand(dut, bank=1, row=80), source_id=2)
    send_lc(dut, bank=0, source_row=81, destination_row=82, source_id=1)

    issued = dut.tick()

    assert [(item.command, item.source_id) for item in issued] == [("ACT_MOV", 1)]
