import pytest

import ramulator
import tests.controller_scheduling.harness as cs


pytestmark = pytest.mark.controller_scheduling


def make_dut(
    *, rank=1, nrefi=None, nrfc=None, refresh_manager=None, row_policy=None
):
    dram_kwargs = {"rank": rank}
    if nrefi is not None:
        dram_kwargs["nREFI"] = nrefi
    if nrfc is not None:
        dram_kwargs["nRFC"] = nrfc
    dram = ramulator.dram.DDR4_PuD_Movement(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        **dram_kwargs,
    )
    return cs.ControllerUnderTest.make_generic_ddr(
        dram,
        refresh_manager=refresh_manager or ramulator.refresh_manager.NoRefresh(),
        row_policy=row_policy or ramulator.row_policy.Open(),
    )


def operand(dut, *, rank=0, bank=0, row=0, column=0):
    return dut.addr_vec(
        Rank=rank,
        BankGroup=0,
        Bank=bank,
        Row=row,
        Column=column,
    )


def send_movement(dut, type_name="LC-MOV", *, rank=0, bank=0, source_id=1):
    mats = (0, 0) if type_name == "LC-MOV" else (0, 1)
    dut.send_movement_request_for_testing(
        type_name,
        [
            operand(dut, rank=rank, bank=bank, row=10, column=3),
            operand(dut, rank=rank, bank=bank, row=11, column=5),
        ],
        *mats,
        source_id,
    )


def tick_until(dut, predicate, max_ticks=256):
    for _ in range(max_ticks):
        match = next((item for item in dut.tick() if predicate(item)), None)
        if match is not None:
            return match
    raise AssertionError("Expected command did not issue")


def terminal_pre(dut, source_id=1):
    owner_pres = [
        item
        for item in dut.history
        if item.source_id == source_id and item.command == "PREpb"
    ]
    return owner_pres[1] if len(owner_pres) >= 2 else None


def test_refresh_queued_before_acquisition_wins_and_movement_waits_for_nrfc():
    dut = make_dut(
        nrefi=64,
        nrfc=2,
        refresh_manager=ramulator.refresh_manager.AllBank(),
    )
    for _ in range(63):
        assert dut.tick() == []
    send_movement(dut)

    refresh = dut.tick()

    assert [item.command for item in refresh] == ["REFab"]
    assert not any(item.command == "ACT_MOV" for item in dut.history)
    assert dut.tick() == []
    first_act = dut.tick()
    assert [item.command for item in first_act] == ["ACT_MOV"]
    assert first_act[0].clk == refresh[0].clk + dut.timings["nRFC"]


def test_refresh_generated_during_ownership_waits_for_terminal_pre_and_nrp():
    dut = make_dut(
        nrefi=64,
        refresh_manager=ramulator.refresh_manager.AllBank(),
    )
    send_movement(dut)
    assert [item.command for item in dut.tick()] == ["ACT_MOV"]

    final_pre = tick_until(dut, lambda item: terminal_pre(dut) is item)
    refresh = tick_until(dut, lambda item: item.command == "REFab")

    assert not any(item.command == "PREab" for item in dut.history)
    assert refresh.clk == final_pre.clk + dut.timings["nRP"]


def test_refresh_for_disjoint_rank_progresses_during_movement_ownership():
    dut = make_dut(
        rank=2,
        nrefi=64,
        refresh_manager=ramulator.refresh_manager.AllBank(),
    )
    send_movement(dut, rank=1)
    assert [item.command for item in dut.tick()] == ["ACT_MOV"]

    rank_level = dut.level_names.index("Rank")
    for _ in range(62):
        dut.tick()
    issued = dut.tick()

    assert [(item.command, item.addr_vec[rank_level]) for item in issued] == [
        ("REFab", 0)
    ]
    assert terminal_pre(dut) is None
    assert not any(
        item.command == "REFab" and item.addr_vec[rank_level] == 1
        for item in dut.history
    )


@pytest.mark.parametrize(
    ("row_policy", "type_name", "expected"),
    [
        (
            ramulator.row_policy.Open(),
            "LC-MOV",
            ["ACT_MOV", "RD_MOV", "PREpb", "ACT_MOV", "WR_MOV", "PREpb"],
        ),
        (
            ramulator.row_policy.ClosedCAP(cap=1),
            "LC-MOV",
            ["ACT_MOV", "RD_MOV", "PREpb", "ACT_MOV", "WR_MOV", "PREpb"],
        ),
        (
            ramulator.row_policy.Open(),
            "GB-MOV",
            ["ACT_MOV", "ACT_MOV", "RD_MOV", "WR_MOV", "PREpb"],
        ),
        (
            ramulator.row_policy.ClosedCAP(cap=1),
            "GB-MOV",
            ["ACT_MOV", "ACT_MOV", "RD_MOV", "WR_MOV", "PREpb"],
        ),
    ],
)
def test_supported_row_policies_do_not_reinterpret_movement(
    row_policy, type_name, expected
):
    dut = make_dut(row_policy=row_policy)
    send_movement(dut, type_name)

    history = dut.run_until_idle(max_ticks=256)

    assert [item.command for item in history] == expected
    assert not any(item.command in ("RDA", "WRA") for item in history)


def test_closedcap_precharge_on_other_bank_progresses_during_movement():
    dut = make_dut(row_policy=ramulator.row_policy.ClosedCAP(cap=1))
    other_bank = operand(dut, bank=1, row=20)
    dut.send_request("Read", other_bank, source_id=2)
    assert [item.command for item in dut.tick()] == ["ACT"]

    send_movement(dut)
    first_act = tick_until(
        dut, lambda item: item.source_id == 1 and item.command == "ACT_MOV"
    )
    policy_pre = tick_until(
        dut, lambda item: item.source_id == -1 and item.command == "PREpb"
    )
    source_pre = tick_until(
        dut, lambda item: item.source_id == 1 and item.command == "PREpb"
    )

    assert first_act.clk < policy_pre.clk < source_pre.clk
