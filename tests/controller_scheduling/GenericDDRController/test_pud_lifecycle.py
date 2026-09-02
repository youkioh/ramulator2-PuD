import pytest

import ramulator
import tests.controller_scheduling.harness as cs
from ramulator._ramulator_test import _PuDRoutingSystemUnderTest


pytestmark = pytest.mark.controller_scheduling


def make_dut(**controller_kwargs):
    dram = ramulator.dram.DDR4_PuD(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    return cs.ControllerUnderTest.make_generic_ddr(dram, **controller_kwargs)


def operand(dut, *, bank=0, row=0, column=0):
    return dut.addr_vec(
        Rank=0,
        BankGroup=0,
        Bank=bank,
        Row=row,
        Column=column,
    )


def first_new_work_after(history, command):
    return next(item for item in history if item.command != command)


@pytest.mark.parametrize(
    ("older_type", "expected_command"),
    [("Read", "ACT"), ("Write", "ACT"), ("RowCopy", "ACT_PUD_S_OC")],
)
def test_oldest_ready_arbitrates_pending_pud_and_read_write(older_type, expected_command):
    dut = make_dut()
    read = operand(dut, bank=1, row=1)
    pud = [operand(dut, bank=0, row=2), operand(dut, bank=0, row=3)]

    if older_type in ("Read", "Write"):
        dut.send_request(older_type, read, source_id=1)
    else:
        dut.send_pud_request("RowCopy", pud, source_id=2)

    dut.priority_send("PREab", operand(dut))
    assert [item.command for item in dut.tick()] == ["PREab"]

    if older_type in ("Read", "Write"):
        dut.send_pud_request("RowCopy", pud, source_id=2)
    else:
        dut.send_request("Read", read, source_id=1)

    dut.run_until_idle(max_ticks=256)
    selected = first_new_work_after(dut.history, "PREab")
    assert selected.command == expected_command


def test_equal_arrival_mixed_arbitration_uses_deterministic_pud_tie_break():
    dut = make_dut()
    dut.send_request("Read", operand(dut, bank=1, row=4), source_id=1)
    dut.send_pud_request(
        "RowCopy",
        [operand(dut, bank=0, row=5), operand(dut, bank=0, row=6)],
        source_id=2,
    )

    assert [item.command for item in dut.tick()] == ["ACT_PUD_S_OC"]


def test_pud_buffer_capacity_is_entry_counted_and_backpressures_without_operand_loss():
    dut = make_dut(pud_buffer_size=1)
    long_rowcopy = [operand(dut, row=row) for row in range(64)]
    blocked_not = [operand(dut, row=100)]

    accepted = dut.try_send_pud_request("RowCopy", long_rowcopy, source_id=1)
    rejected = dut.try_send_pud_request("NOT", blocked_not, source_id=2)

    assert accepted["accepted"] is True
    assert rejected["accepted"] is False
    assert rejected["operands"] == blocked_not
    assert rejected["arrive"] == -1

    assert [item.command for item in dut.tick()] == ["ACT_PUD_S_OC"]
    retried = dut.try_send_pud_request("NOT", blocked_not, source_id=2)
    assert retried["accepted"] is True
    assert retried["operands"] == blocked_not


def test_pud_buffer_default_capacity_is_32_entries():
    dut = make_dut()
    for row in range(32):
        assert dut.try_send_pud_request(
            "NOT", [operand(dut, row=row)], source_id=row
        )["accepted"]

    assert not dut.try_send_pud_request(
        "NOT", [operand(dut, row=32)], source_id=32
    )["accepted"]


@pytest.mark.parametrize("type_name", ["RowCopy", "NOT"])
def test_pud_callback_waits_for_final_precharge_recovery(type_name):
    dut = make_dut()
    operands = (
        [operand(dut, row=110), operand(dut, row=111)]
        if type_name == "RowCopy"
        else [operand(dut, row=112)]
    )
    dut.send_pud_request(type_name, operands, source_id=7)

    final_pre = None
    while final_pre is None:
        issued = dut.tick()
        final_pre = next((item for item in issued if item.command == "PREpb"), None)

    assert dut.completions() == []
    for _ in range(dut.timings["nRP"] - 1):
        dut.tick()
        assert dut.completions() == []

    dut.tick()
    assert dut.completions() == [
        {
            "type_id": dut._request_type_ids[type_name],
            "source_id": 7,
            "arrive": 0,
            "depart": final_pre.clk + dut.timings["nRP"],
        }
    ]


def test_final_precharge_releases_bank_before_pud_callback():
    dut = make_dut()
    bank = operand(dut, row=120)
    dut.send_pud_request("NOT", [bank], source_id=1)

    while not any(item.command == "PREpb" for item in dut.history):
        dut.tick()
    final_pre = dut.history[-1]
    assert dut.completions() == []

    dut.priority_send("PREpb", bank)
    issued = dut.tick()
    assert [(item.command, item.source_id) for item in issued] == [("PREpb", -2)]
    assert issued[0].clk == final_pre.clk + 1
    assert dut.completions() == []


def test_mixed_completion_queue_handles_departure_reordering():
    dut = make_dut()
    dut.send_pud_request(
        "RowCopy",
        [operand(dut, bank=0, row=130), operand(dut, bank=0, row=131)],
        source_id=1,
    )
    assert [item.command for item in dut.tick()] == ["ACT_PUD_S_OC"]

    for _ in range(27):
        dut.tick()
    dut.send_request("Read", operand(dut, bank=1, row=132), source_id=2)
    dut.run_until_idle(max_ticks=256)

    read_issue = next(item for item in dut.history if item.command == "RD")
    pud_pre = next(
        item
        for item in dut.history
        if item.command == "PREpb" and item.source_id == 1
    )
    completions = dut.completions()
    assert read_issue.clk < pud_pre.clk
    assert completions[0]["source_id"] == 1
    assert completions[1]["source_id"] == 2
    assert completions[0]["depart"] < completions[1]["depart"]


def test_completion_callback_can_append_write_forwarded_read_completion():
    dut = make_dut()
    initial = operand(dut, bank=0, row=133)
    forwarded = operand(dut, bank=1, row=134)
    dut.send_read_with_reentrant_forwarded_read(
        initial,
        source_id=1,
        forwarded_addr_vec=forwarded,
        forwarded_source_id=2,
    )

    initial_read = None
    while initial_read is None:
        initial_read = next(
            (item for item in dut.tick() if item.command == "RD"), None
        )

    read_latency = dut.timings["nCL"] + dut.timings["nBL"]
    for _ in range(read_latency - 1):
        dut.tick()
    assert dut.completions() == []

    dut.send_request("Write", forwarded, source_id=3)
    dut.tick()
    assert [item["source_id"] for item in dut.completions()] == [1]

    dut.tick()
    assert [item["source_id"] for item in dut.completions()] == [1, 2]
    assert dut.completions()[0]["depart"] == initial_read.clk + read_latency
    assert dut.completions()[1]["depart"] == dut.completions()[0]["depart"] + 1

    dut.run_until_idle(max_ticks=256)
    for _ in range(2):
        dut.tick()
    assert [item["source_id"] for item in dut.completions()] == [1, 2]


def test_pud_controller_statistics_are_operation_based_and_exclude_rw_counters():
    dut = make_dut()
    requests = {
        "RowCopy": [140, 141],
        "MAJ3": [142, 143, 144],
        "MAJ5": [145, 146, 147, 148, 149],
        "NOT": [150],
    }
    for bank, (type_name, rows) in enumerate(requests.items()):
        dut.send_pud_request(
            type_name,
            [operand(dut, bank=bank, row=row) for row in rows],
            source_id=bank,
        )
    dut.run_until_idle(max_ticks=512)

    stats = dut.stats()
    completions = {item["type_id"]: item for item in dut.completions()}
    for type_name in requests:
        stat_name = type_name.lower()
        completion = completions[dut._request_type_ids[type_name]]
        latency = completion["depart"] - completion["arrive"]
        assert stats[f"num_pud_{stat_name}_reqs"] == 1
        assert stats[f"num_pud_{stat_name}_reqs_completed"] == 1
        assert stats[f"pud_{stat_name}_latency"] == latency
        assert stats[f"avg_pud_{stat_name}_latency"] == latency

    assert stats["pud_queue_len"] > 0
    assert stats["pud_queue_len_avg"] > 0
    assert stats["queue_len"] >= stats["pud_queue_len"]
    assert stats["num_read_reqs"] == 0
    assert stats["num_write_reqs"] == 0
    assert stats["row_hits"] == 0
    assert stats["row_misses"] == 0
    assert stats["row_conflicts"] == 0
    assert stats["read_throughput_MBps"] == 0
    assert stats["write_throughput_MBps"] == 0


def test_generic_memory_system_counts_accepted_pud_operations():
    dut = make_dut()
    system = _PuDRoutingSystemUnderTest(num_channels=1)
    requests = {
        "RowCopy": [160, 161],
        "MAJ3": [162, 163, 164],
        "MAJ5": [165, 166, 167, 168, 169],
        "NOT": [170],
    }
    for type_name, rows in requests.items():
        system.send_pud_request(
            dut._request_type_ids[type_name],
            [operand(dut, row=row) for row in rows],
        )

    stats = system.stats()
    for type_name in requests:
        assert stats[f"total_num_pud_{type_name.lower()}_requests"] == 1


def test_standard_ddr4_controller_statistics_do_not_gain_pud_fields():
    dram = ramulator.dram.DDR4(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    dut = cs.ControllerUnderTest.make_generic_ddr(dram)

    stats = dut.stats()
    assert "pud_queue_len" not in stats
    assert "num_pud_rowcopy_reqs" not in stats
