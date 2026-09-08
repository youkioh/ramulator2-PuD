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


def run_request(dram_class, type_name, rows):
    dut = make_dut(dram_class)
    operands = [operand(dut, row, column) for column, row in enumerate(rows)]
    if type_name in ("Read", "Write"):
        dut.send_request(type_name, operands[0], source_id=9)
    else:
        dut.send_pud_request(type_name, operands, source_id=9)
    history = dut.run_until_idle(max_ticks=256)
    return dut, history


@pytest.mark.parametrize(
    ("type_name", "rows"),
    [
        ("Read", [1]),
        ("Write", [2]),
        ("RowCopy", [10, 11]),
        ("MAJ3", [20, 21, 22]),
        ("MAJ5", [30, 31, 32, 33, 34]),
        ("NOT", [40]),
    ],
)
def test_combined_skeleton_matches_ddr4_pud_request_behavior(type_name, rows):
    baseline, baseline_history = run_request(ramulator.dram.DDR4_PuD, type_name, rows)
    combined, combined_history = run_request(ramulator.dram.DDR4_PuD_Movement, type_name, rows)

    assert combined_history == baseline_history
    assert combined.completions() == baseline.completions()
    combined_stats = combined.stats()
    baseline_stats = baseline.stats()
    inherited_combined_stats = {
        name: value
        for name, value in combined_stats.items()
        if "lcmov" not in name and "gbmov" not in name
    }
    assert inherited_combined_stats == baseline_stats


def test_combined_standard_advertises_both_movement_requests():
    dut = make_dut(ramulator.dram.DDR4_PuD_Movement)

    assert tuple(type(dut.dram).supported_requests)[-2:] == ("LC-MOV", "GB-MOV")
