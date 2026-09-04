import pytest

import ramulator
import tests.controller_scheduling.harness as cs
from ramulator._ramulator_test import _PuDRoutingSystemUnderTest
from ramulator.dram.spec import REQUEST_TYPE_IDS


pytestmark = pytest.mark.controller_scheduling


def make_dut(*, hffs_per_mat=4, pud_buffer_size=32):
    dram = ramulator.dram.DDR4_PuD_Movement(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
        hffs_per_mat=hffs_per_mat,
    )
    return cs.ControllerUnderTest.make_generic_ddr(
        dram,
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
        row_policy=ramulator.row_policy.Open(),
        pud_buffer_size=pud_buffer_size,
    )


def operand(dut, *, bank=0, row=0, column=0):
    return dut.addr_vec(
        Rank=0,
        BankGroup=0,
        Bank=bank,
        Row=row,
        Column=column,
    )


def send_movement(dut, type_name, mats, *, bank=0, source_id=1):
    dut.send_movement_request_for_testing(
        type_name,
        [
            operand(dut, bank=bank, row=10, column=3),
            operand(dut, bank=bank, row=11, column=5),
        ],
        *mats,
        source_id,
    )


def tick_until_terminal_pre(dut, type_name, source_id=1, max_ticks=256):
    terminal_index = 2 if type_name == "LC-MOV" else 1
    seen = 0
    for _ in range(max_ticks):
        for issued in dut.tick():
            if issued.source_id == source_id and issued.command == "PREpb":
                seen += 1
                if seen == terminal_index:
                    return issued
    raise AssertionError("Movement terminal PREpb did not issue")


@pytest.mark.parametrize("type_name", ["LC-MOV", "GB-MOV"])
def test_accepted_incomplete_request_has_only_accepted_count(type_name):
    dut = make_dut()
    mats = (2, 5) if type_name == "LC-MOV" else (2, 3)
    stat_name = type_name.lower().replace("-", "")

    send_movement(dut, type_name, mats)
    stats = dut.sample_stats()

    assert stats[f"num_pud_{stat_name}_reqs"] == 1
    assert stats[f"num_pud_{stat_name}_reqs_completed"] == 0
    assert stats[f"pud_{stat_name}_latency"] == 0
    assert stats[f"avg_pud_{stat_name}_latency"] == 0
    assert stats[f"pud_{stat_name}_moved_bits"] == 0


def test_backpressured_movement_does_not_increment_accepted_count():
    dut = make_dut(pud_buffer_size=1)
    operands = [operand(dut, row=10), operand(dut, row=11)]
    first = dut.try_send_movement_request_for_testing(
        "LC-MOV", operands, 0, 0, source_id=1
    )
    rejected = dut.try_send_movement_request_for_testing(
        "LC-MOV", operands, 1, 1, source_id=2
    )

    assert first["accepted"] is True
    assert rejected == {"accepted": False, "arrive": -1}
    stats = dut.sample_stats()
    assert stats["num_pud_lcmov_reqs"] == 1


@pytest.mark.parametrize(
    ("type_name", "mats", "expected_bits"),
    [
        ("LC-MOV", (0, 0), 7),
        ("LC-MOV", (4, 8), 35),
        ("LC-MOV", (112, 127), 112),
        ("GB-MOV", (4, 5), 7),
    ],
)
def test_completion_accounts_latency_and_exact_bits_at_terminal_recovery(
    type_name, mats, expected_bits
):
    dut = make_dut(hffs_per_mat=7)
    stat_name = type_name.lower().replace("-", "")
    send_movement(dut, type_name, mats)
    terminal = tick_until_terminal_pre(dut, type_name)

    at_terminal = dut.sample_stats()
    assert at_terminal[f"num_pud_{stat_name}_reqs_completed"] == 0
    assert at_terminal[f"pud_{stat_name}_latency"] == 0
    assert at_terminal[f"pud_{stat_name}_moved_bits"] == 0

    for _ in range(dut.timings["nRP"] - 1):
        dut.tick()
        before_recovery = dut.sample_stats()
        assert before_recovery[f"num_pud_{stat_name}_reqs_completed"] == 0

    dut.tick()
    completed = dut.sample_stats()
    completion = dut.completions()[0]
    expected_latency = completion["depart"] - completion["arrive"]

    assert completion["depart"] == terminal.clk + dut.timings["nRP"]
    assert completed[f"num_pud_{stat_name}_reqs_completed"] == 1
    assert completed[f"pud_{stat_name}_latency"] == expected_latency
    assert completed[f"avg_pud_{stat_name}_latency"] == expected_latency
    assert completed[f"pud_{stat_name}_moved_bits"] == expected_bits

    callback_stats = dut.completion_callback_stats()[0]
    assert callback_stats[f"num_pud_{stat_name}_reqs_completed"] == 1
    assert callback_stats[f"pud_{stat_name}_latency"] == expected_latency
    assert callback_stats[f"pud_{stat_name}_moved_bits"] == expected_bits


def test_movement_is_excluded_from_ordinary_read_write_throughput():
    dut = make_dut()
    send_movement(dut, "LC-MOV", (1, 6), bank=0, source_id=1)
    send_movement(dut, "GB-MOV", (6, 7), bank=1, source_id=2)
    dut.run_until_idle(max_ticks=512)

    stats = dut.sample_stats()
    assert stats["num_read_reqs"] == 0
    assert stats["num_write_reqs"] == 0
    assert stats["num_read_reqs_served"] == 0
    assert stats["num_write_reqs_served"] == 0
    assert stats["read_throughput_MBps"] == 0
    assert stats["write_throughput_MBps"] == 0
    assert stats["total_throughput_MBps"] == 0


@pytest.mark.parametrize("dram_class", [ramulator.dram.DDR4, ramulator.dram.DDR4_PuD])
def test_existing_ddr4_standards_do_not_gain_movement_statistics(dram_class):
    dram = dram_class(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    dut = cs.ControllerUnderTest.make_generic_ddr(dram)

    assert not any("lcmov" in name or "gbmov" in name for name in dut.sample_stats())


def test_memory_system_counts_accepted_movement_requests_across_channels_once():
    system = _PuDRoutingSystemUnderTest(num_channels=2)
    lc = [[0, 0], [0, 1]]
    gb = [[1, 0], [1, 1]]

    system.send_movement_request(
        REQUEST_TYPE_IDS["LC-MOV"], lc, "LC", 2, 5, retry_once=True
    )
    system.send_movement_request(REQUEST_TYPE_IDS["GB-MOV"], gb, "GB", 6, 7)
    system.send_movement_request(REQUEST_TYPE_IDS["LC-MOV"], lc, "LC", 10, 10)

    stats = system.stats()
    assert stats["total_num_pud_lcmov_requests"] == 2
    assert stats["total_num_pud_gbmov_requests"] == 1
