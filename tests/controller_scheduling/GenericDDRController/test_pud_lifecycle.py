import pytest

import ramulator
import tests.controller_scheduling.harness as cs


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
