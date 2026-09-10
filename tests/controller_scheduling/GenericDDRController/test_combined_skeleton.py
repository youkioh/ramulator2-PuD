import pytest

import ramulator
import tests.controller_scheduling.harness as cs

pytestmark = pytest.mark.controller_scheduling


def make_dut(dram_class):
    dram = dram_class(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )
    return cs.ControllerUnderTest.make_generic_ddr(dram, num_cores=10)


def operand(dut, row, column=0):
    return dut.addr_vec(Rank=0, BankGroup=0, Bank=0, Row=row, Column=column)


@pytest.mark.parametrize(("type_name", "row"), [("Read", 1), ("Write", 2)])
def test_combined_standard_preserves_ordinary_ddr4_behavior(type_name, row):
    baseline = make_dut(ramulator.dram.DDR4_PuD)
    combined = make_dut(ramulator.dram.DDR4_PuD_Movement)
    for dut in (baseline, combined):
        dut.send_request(type_name, operand(dut, row), source_id=9)

    baseline_history = baseline.run_until_idle(max_ticks=256)
    combined_history = combined.run_until_idle(max_ticks=256)

    assert combined_history == baseline_history
    assert combined.completions() == baseline.completions()


def test_combined_standard_advertises_both_movement_requests():
    dut = make_dut(ramulator.dram.DDR4_PuD_Movement)

    assert tuple(type(dut.dram).supported_requests)[-2:] == ("LC-MOV", "GB-MOV")
