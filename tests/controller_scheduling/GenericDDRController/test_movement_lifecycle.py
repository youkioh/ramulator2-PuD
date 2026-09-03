import pytest

import ramulator
import tests.controller_scheduling.harness as cs


pytestmark = pytest.mark.controller_scheduling


def make_dut(**timing_overrides):
    dram = ramulator.dram.DDR4_PuD_Movement(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
        **timing_overrides,
    )
    return cs.ControllerUnderTest.make_generic_ddr(
        dram,
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
        row_policy=ramulator.row_policy.Open(),
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


def movement_operands(dut, *, bank=0, source_row=0, destination_row=1):
    return [
        operand(dut, bank=bank, row=source_row, column=3),
        operand(dut, bank=bank, row=destination_row, column=5),
    ]


def send_movement(dut, type_name, *, bank=0, source_id=1):
    mats = (0, 0) if type_name == "LC-MOV" else (0, 1)
    dut.send_movement_request_for_testing(
        type_name,
        movement_operands(dut, bank=bank, source_row=10, destination_row=11),
        *mats,
        source_id,
    )


def tick_until_terminal_pre(dut, type_name, source_id=1, max_ticks=256):
    pre_count = 2 if type_name == "LC-MOV" else 1
    for _ in range(max_ticks):
        issued = dut.tick()
        for item in issued:
            if item.source_id != source_id or item.command != "PREpb":
                continue
            seen = [
                entry
                for entry in dut.history
                if entry.source_id == source_id and entry.command == "PREpb"
            ]
            if len(seen) == pre_count:
                return item
    raise AssertionError("Movement terminal PREpb did not issue")


@pytest.mark.parametrize("type_name", ["LC-MOV", "GB-MOV"])
def test_movement_depart_and_callback_follow_terminal_precharge_recovery(type_name):
    dut = make_dut()
    send_movement(dut, type_name, source_id=3)

    terminal = tick_until_terminal_pre(dut, type_name, source_id=3)
    assert dut.completions() == []

    for _ in range(dut.timings["nRP"] - 1):
        dut.tick()
        assert dut.completions() == []

    dut.tick()
    assert dut.completions() == [
        {
            "type_id": dut._request_type_ids[type_name],
            "source_id": 3,
            "arrive": 0,
            "depart": terminal.clk + dut.timings["nRP"],
        }
    ]

    for _ in range(3):
        dut.tick()
    assert len(dut.completions()) == 1
    assert not any("mov" in name.lower() for name in dut.stats())


def test_movement_completion_queue_handles_departure_reordering():
    dut = make_dut(nCL=200)
    open_row = operand(dut, bank=1, row=20)
    dut.send_request("Write", open_row, source_id=8)
    dut.run_until_idle(max_ticks=128)

    send_movement(dut, "LC-MOV", bank=0, source_id=1)
    assert [(item.command, item.source_id) for item in dut.tick()] == [
        ("ACT_MOV", 1)
    ]
    dut.tick()
    dut.send_request("Read", open_row, source_id=2)
    read_issue = None
    for _ in range(32):
        read_issue = next(
            (item for item in dut.tick() if item.command == "RD" and item.source_id == 2),
            None,
        )
        if read_issue is not None:
            break
    assert read_issue is not None
    assert not any(
        item.source_id == 1 and item.command == "PREpb" for item in dut.history
    )

    dut.run_until_idle(max_ticks=512)
    completions = dut.completions()
    assert [item["source_id"] for item in completions] == [1, 2]
    assert completions[0]["depart"] < completions[1]["depart"]


def test_movement_callback_can_append_forwarded_read_completion():
    dut = make_dut()
    operands = movement_operands(dut, bank=0, source_row=30, destination_row=31)
    forwarded = operand(dut, bank=0, row=32)
    dut.send_movement_with_reentrant_forwarded_read(
        "GB-MOV", operands, 0, 1, 1, forwarded, 2
    )
    assert [(item.command, item.source_id) for item in dut.tick()] == [
        ("ACT_MOV", 1)
    ]
    dut.send_request("Write", forwarded, source_id=3)

    dut.run_until_idle(max_ticks=256)
    completions = dut.completions()
    assert [item["source_id"] for item in completions] == [1, 2]
    assert completions[1]["depart"] == completions[0]["depart"] + 1

    for _ in range(3):
        dut.tick()
    assert [item["source_id"] for item in dut.completions()] == [1, 2]
