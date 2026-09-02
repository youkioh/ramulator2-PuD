import pytest

import ramulator
import tests.controller_scheduling.harness as cs


pytestmark = pytest.mark.controller_scheduling


def make_dut(*, refresh_manager=None, nrefi=None):
    dram_kwargs = {}
    if nrefi is not None:
        dram_kwargs["nREFI"] = nrefi
    dram = ramulator.dram.DDR4_PuD(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
        **dram_kwargs,
    )
    return cs.ControllerUnderTest.make_generic_ddr(
        dram,
        refresh_manager=refresh_manager or ramulator.refresh_manager.NoRefresh(),
    )


def operand(dut, *, bank=0, row=0, column=0):
    return dut.addr_vec(
        Rank=0,
        BankGroup=0,
        Bank=bank,
        Row=row,
        Column=column,
    )


@pytest.mark.parametrize(
    ("type_name", "rows", "commands", "gaps"),
    [
        ("RowCopy", [10, 11], ["ACT_PUD_S_OC", "ACT_PUD", "PREpb"], [40, 5]),
        (
            "RowCopy",
            [20, 21, 22, 23],
            ["ACT_PUD_S_OC", "ACT_PUD", "ACT_PUD", "ACT_PUD", "PREpb"],
            [40, 5, 5, 5],
        ),
        (
            "MAJ3",
            [30, 31, 32],
            ["ACT_PUD_OC", "ACT_PUD", "ACT_PUD_S", "PREpb"],
            [11, 5, 34],
        ),
        (
            "MAJ5",
            [40, 41, 42, 43, 44],
            ["ACT_PUD_OC", "ACT_PUD", "ACT_PUD", "ACT_PUD", "ACT_PUD_S", "PREpb"],
            [11, 5, 5, 5, 34],
        ),
        ("NOT", [50], ["ACT_PUD_S_OC", "N", "PREpb"], [40, 43]),
    ],
)
def test_pud_sequence_progression_and_operand_selection(type_name, rows, commands, gaps):
    dut = make_dut()
    row_level = dut.level_names.index("Row")
    operands = [operand(dut, row=row, column=i) for i, row in enumerate(rows)]

    dut.send_pud_request(type_name, operands, source_id=7)
    history = dut.run_until_idle(max_ticks=256)

    dut.assert_commands(commands, history=history)
    expected_command_rows = rows if type_name != "NOT" else [rows[0], rows[0]]
    assert [item.addr_vec[row_level] for item in history[:-1]] == expected_command_rows
    assert history[-1].addr_vec[row_level] == rows[-1]
    assert all(item.source_id == 7 for item in history)
    for i, gap in enumerate(gaps):
        dut.assert_gap(i, i + 1, gap, history=history)


def test_same_bank_request_waits_for_pud_final_precharge():
    dut = make_dut()
    pud_operands = [operand(dut, bank=0, row=60), operand(dut, bank=0, row=61)]

    dut.send_pud_request("RowCopy", pud_operands, source_id=1)
    first = dut.tick()
    assert [item.command for item in first] == ["ACT_PUD_S_OC"]

    dut.send_request("Read", operand(dut, bank=0, row=62), source_id=2)
    dut.run_until_idle(max_ticks=256)

    owner_pre = next(
        i
        for i, item in enumerate(dut.history)
        if item.command == "PREpb" and item.source_id == 1
    )
    competing_act = next(
        i
        for i, item in enumerate(dut.history)
        if item.command == "ACT" and item.source_id == 2
    )
    assert competing_act > owner_pre


def test_opened_bank_precharge_does_not_advance_pud_sequence():
    dut = make_dut()
    opened = operand(dut, bank=0, row=63)
    operands = [operand(dut, bank=0, row=64), operand(dut, bank=0, row=65)]

    dut.send_request("Read", opened, source_id=2)
    dut.run_until_idle(max_ticks=128)
    dut.send_pud_request("RowCopy", operands, source_id=1)
    history = dut.run_until_idle(max_ticks=256)

    dut.assert_commands(
        ["PREpb", "ACT_PUD_S_OC", "ACT_PUD", "PREpb"],
        history=history,
    )
    dut.assert_gap(0, 1, dut.timings["nRP"], history=history)
    assert history[0].source_id == 1
    assert history[1].addr_vec == operands[0]
    assert history[2].addr_vec == operands[1]


def test_other_bank_active_request_interleaves_during_pud_timing_stall():
    dut = make_dut()
    dut.send_request("Read", operand(dut, bank=1, row=70), source_id=2)
    assert [item.command for item in dut.tick()] == ["ACT"]

    dut.send_pud_request(
        "RowCopy",
        [operand(dut, bank=0, row=71), operand(dut, bank=0, row=72)],
        source_id=1,
    )
    dut.run_until_idle(max_ticks=256)

    pud_open = next(
        i for i, item in enumerate(dut.history) if item.command == "ACT_PUD_S_OC"
    )
    other_read = next(
        i
        for i, item in enumerate(dut.history)
        if item.command == "RD" and item.source_id == 2
    )
    pud_destination = next(
        i for i, item in enumerate(dut.history) if item.command == "ACT_PUD"
    )
    assert pud_open < other_read < pud_destination


def test_same_bank_priority_precharge_waits_for_pud_owner():
    dut = make_dut()
    bank = operand(dut, bank=0, row=80)
    dut.send_pud_request("NOT", [bank], source_id=1)
    assert [item.command for item in dut.tick()] == ["ACT_PUD_S_OC"]

    dut.priority_send("PREpb", bank)
    dut.run_until_idle(max_ticks=256)

    precharges = [item for item in dut.history if item.command == "PREpb"]
    assert [item.source_id for item in precharges] == [1, -2]


def test_all_bank_refresh_remains_queued_until_pud_final_precharge():
    dut = make_dut(
        refresh_manager=ramulator.refresh_manager.AllBank(),
        nrefi=8,
    )
    dut.send_pud_request(
        "RowCopy",
        [operand(dut, bank=0, row=90), operand(dut, bank=0, row=91)],
        source_id=1,
    )

    for _ in range(96):
        dut.tick()

    owner_pre = next(
        item
        for item in dut.history
        if item.command == "PREpb" and item.source_id == 1
    )
    refreshes = [item for item in dut.history if item.command == "REFab"]
    assert refreshes
    assert all(item.clk > owner_pre.clk for item in refreshes)
