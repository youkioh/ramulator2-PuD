import pytest

import ramulator
from ramulator._ramulator_test import _PuDRoutingSystemUnderTest
from tests.controller_scheduling.harness import ControllerUnderTest


def make_dut(dram_cls=ramulator.dram.DDR4_PuD):
    dram = dram_cls(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=2,
    )
    return ControllerUnderTest.make_generic_ddr(dram)


def operand(dut, *, channel=0, rank=0, bankgroup=0, bank=0, row=0, column=0):
    return dut.addr_vec(
        Channel=channel,
        Rank=rank,
        BankGroup=bankgroup,
        Bank=bank,
        Row=row,
        Column=column,
    )


@pytest.mark.parametrize(
    ("type_name", "rows"),
    [
        ("RowCopy", [3, 5]),
        ("MAJ3", [3, 5, 7]),
        ("MAJ5", [3, 5, 7, 9, 11]),
        ("NOT", [3]),
    ],
)
def test_pud_requests_preserve_type_and_ordered_operands(type_name, rows):
    dut = make_dut()
    operands = [operand(dut, row=row, column=i) for i, row in enumerate(rows)]

    stored = dut.send_pud_request(type_name, operands, source_id=4)

    assert stored["type_id"] == dut._request_type_ids[type_name]
    assert stored["operands"] == operands
    assert stored["addr_vec"] == operands[0]
    assert stored["source_id"] == 4


def test_rowcopy_preserves_large_destination_list():
    dut = make_dut()
    operands = [operand(dut, row=row) for row in range(512)]

    stored = dut.send_pud_request("RowCopy", operands)

    assert stored["operands"] == operands


@pytest.mark.parametrize(
    ("type_name", "count"),
    [("RowCopy", 1), ("MAJ3", 2), ("MAJ3", 4), ("MAJ5", 4), ("MAJ5", 6), ("NOT", 0), ("NOT", 2)],
)
def test_invalid_operand_counts_are_rejected(type_name, count):
    dut = make_dut()
    operands = [operand(dut, row=i) for i in range(count)]

    with pytest.raises(RuntimeError, match="invalid operand count"):
        dut.send_pud_request(type_name, operands)


def test_routing_uses_operand_zero_and_requires_one_channel():
    dut = make_dut()
    same_channel = [operand(dut, channel=1, row=1), operand(dut, channel=1, row=2)]
    mixed_channels = [operand(dut, channel=1, row=1), operand(dut, channel=0, row=2)]

    assert dut.validate_pud_routing("RowCopy", same_channel, num_channels=2) == 1
    with pytest.raises(RuntimeError, match="must share a channel"):
        dut.validate_pud_routing("RowCopy", mixed_channels, num_channels=2)


def test_generic_dram_system_routes_to_operand_zero_channel():
    dut = make_dut()
    system = _PuDRoutingSystemUnderTest(num_channels=2)
    operands = [operand(dut, channel=1, row=1), operand(dut, channel=1, row=2)]

    routed = system.send_pud_request(dut._request_type_ids["RowCopy"], operands)

    assert routed["receiver"] == 1
    assert [list(item) for item in routed["operands"]] == operands


def test_invalid_operation_and_channel_coordinates_are_rejected():
    dut = make_dut()
    operands = [operand(dut, row=1), operand(dut, row=2)]

    with pytest.raises(RuntimeError, match="does not support request type_id"):
        dut._cpp.send_pud_request(99, operands)
    with pytest.raises(RuntimeError, match="no channel coordinate"):
        dut._cpp.send_pud_request(dut._request_type_ids["RowCopy"], [[], []])
    with pytest.raises(RuntimeError, match="outside"):
        dut.validate_pud_routing(
            "RowCopy", [operand(dut, channel=2), operand(dut, channel=2)], 2
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("rank", 1, "share Rank"),
        ("bankgroup", 1, "share BankGroup"),
        ("bank", 1, "share Bank"),
        ("row", 1024, "share a logical subarray"),
    ],
)
def test_controller_rejects_placement_mismatch(field, value, message):
    dut = make_dut()
    kwargs = {field: value}
    operands = [operand(dut, row=0), operand(dut, **kwargs)]

    with pytest.raises(RuntimeError, match=message):
        dut.send_pud_request("RowCopy", operands)


def test_columns_are_preserved_but_do_not_affect_placement():
    dut = make_dut()
    operands = [operand(dut, row=0, column=0), operand(dut, row=1023, column=127)]

    stored = dut.send_pud_request("RowCopy", operands)

    assert stored["operands"] == operands


def test_pud_ingress_starts_controller_sequence():
    dut = make_dut()
    operands = [operand(dut, row=1), operand(dut, row=2)]

    dut.send_pud_request("RowCopy", operands)

    issued = dut.tick()
    assert [item.command for item in issued] == ["ACT_PUD_S_OC"]
    assert issued[0].addr_vec == operands[0]


def test_controller_rejects_bad_shape_and_bounds():
    dut = make_dut()
    good = operand(dut, row=1)

    with pytest.raises(RuntimeError, match="hierarchy coordinates"):
        dut.send_pud_request("RowCopy", [good, good[:-1]])

    out_of_bounds = operand(dut, row=1)
    out_of_bounds[4] = 1 << 16
    with pytest.raises(RuntimeError, match="outside"):
        dut.send_pud_request("RowCopy", [good, out_of_bounds])


def test_standard_ddr4_rejects_pud_request_types():
    dut = make_dut(ramulator.dram.DDR4)
    operands = [operand(dut, row=1), operand(dut, row=2)]

    with pytest.raises(RuntimeError, match="does not support request type_id"):
        dut._cpp.send_pud_request(2, operands)
