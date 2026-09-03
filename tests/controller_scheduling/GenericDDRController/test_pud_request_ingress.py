import pytest
from ramulator._ramulator_test import (
    _internal_request_default_size,
    _PuDRoutingSystemUnderTest,
    _request_size_contract,
)
from ramulator.dram.spec import REQUEST_TYPE_IDS

import ramulator
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


@pytest.mark.parametrize(
    ("type_name", "metadata_kind", "first_mat", "second_mat"),
    [
        ("LC-MOV", "LC", 7, 23),
        ("GB-MOV", "GB", 7, 8),
    ],
)
def test_movement_ingress_preserves_typed_metadata_and_ordered_operands(
    type_name, metadata_kind, first_mat, second_mat
):
    dut = make_dut(ramulator.dram.DDR4_PuD_Movement)
    system = _PuDRoutingSystemUnderTest(num_channels=2)
    operands = [
        operand(dut, channel=1, row=4, column=9),
        operand(dut, channel=1, row=5, column=10),
    ]

    routed = system.send_movement_request(
        REQUEST_TYPE_IDS[type_name],
        operands,
        metadata_kind,
        first_mat,
        second_mat,
    )

    assert routed["receiver"] == 1
    assert [list(item) for item in routed["operands"]] == operands
    assert routed["size_bytes"] == -1
    assert routed["metadata_kind"] == metadata_kind
    assert routed["first_mat"] == first_mat
    assert routed["second_mat"] == second_mat


@pytest.mark.parametrize("type_name", ["LC-MOV", "GB-MOV"])
@pytest.mark.parametrize("count", [0, 1, 3])
def test_movement_requires_exactly_two_operands(type_name, count):
    dut = make_dut(ramulator.dram.DDR4_PuD_Movement)
    system = _PuDRoutingSystemUnderTest(num_channels=1)
    operands = [operand(dut, row=i) for i in range(count)]
    metadata_kind = "LC" if type_name == "LC-MOV" else "GB"

    with pytest.raises(RuntimeError, match="invalid operand count"):
        system.send_movement_request(
            REQUEST_TYPE_IDS[type_name], operands, metadata_kind, 1, 2
        )


@pytest.mark.parametrize(
    ("type_name", "metadata_kind"),
    [
        ("LC-MOV", ""),
        ("LC-MOV", "GB"),
        ("GB-MOV", ""),
        ("GB-MOV", "LC"),
    ],
)
def test_movement_rejects_missing_or_wrong_typed_metadata(type_name, metadata_kind):
    dut = make_dut(ramulator.dram.DDR4_PuD_Movement)
    system = _PuDRoutingSystemUnderTest(num_channels=1)
    operands = [operand(dut, row=1), operand(dut, row=2)]

    with pytest.raises(RuntimeError, match="required typed movement metadata"):
        system.send_movement_request(
            REQUEST_TYPE_IDS[type_name], operands, metadata_kind, 1, 2
        )


@pytest.mark.parametrize("type_name", ["LC-MOV", "GB-MOV"])
def test_movement_routing_uses_operand_zero_and_requires_same_valid_channel(type_name):
    dut = make_dut(ramulator.dram.DDR4_PuD_Movement)
    system = _PuDRoutingSystemUnderTest(num_channels=2)
    type_id = REQUEST_TYPE_IDS[type_name]
    metadata_kind = "LC" if type_name == "LC-MOV" else "GB"

    same_channel = [operand(dut, channel=1, row=1), operand(dut, channel=1, row=2)]
    routed = system.send_movement_request(
        type_id, same_channel, metadata_kind, 1, 2
    )
    assert routed["receiver"] == 1

    mixed_channels = [operand(dut, channel=1, row=1), operand(dut, channel=0, row=2)]
    with pytest.raises(RuntimeError, match="must share a channel"):
        system.send_movement_request(
            type_id, mixed_channels, metadata_kind, 1, 2
        )

    for bad_operand in (0, 1):
        invalid = [operand(dut, row=1), operand(dut, row=2)]
        invalid[bad_operand][0] = 2
        with pytest.raises(RuntimeError, match=rf"operand {bad_operand}.*outside"):
            system.send_movement_request(
                type_id, invalid, metadata_kind, 1, 2
            )


@pytest.mark.parametrize("type_name", ["LC-MOV", "GB-MOV"])
@pytest.mark.parametrize("size_bytes", [-2, 0, 1, 64, 65])
def test_movement_accepts_only_named_size_na_contract(type_name, size_bytes):
    dut = make_dut(ramulator.dram.DDR4_PuD_Movement)
    system = _PuDRoutingSystemUnderTest(num_channels=1)
    operands = [operand(dut, row=1), operand(dut, row=2)]
    metadata_kind = "LC" if type_name == "LC-MOV" else "GB"

    with pytest.raises(RuntimeError, match="N/A sentinel -1"):
        system.send_movement_request(
            REQUEST_TYPE_IDS[type_name],
            operands,
            metadata_kind,
            1,
            2,
            size_bytes=size_bytes,
        )


def test_movement_metadata_survives_copy_and_backpressure_retry():
    dut = make_dut(ramulator.dram.DDR4_PuD_Movement)
    system = _PuDRoutingSystemUnderTest(num_channels=1)
    operands = [operand(dut, row=1), operand(dut, row=2)]

    routed = system.send_movement_request(
        REQUEST_TYPE_IDS["LC-MOV"],
        operands,
        "LC",
        12,
        19,
        retry_once=True,
    )

    assert [list(item) for item in routed["operands"]] == operands
    assert routed["metadata_kind"] == "LC"
    assert (routed["first_mat"], routed["second_mat"]) == (12, 19)


@pytest.mark.parametrize("type_id", [0, 1, 2, 3, 4, 5])
@pytest.mark.parametrize("size_bytes", [1, 64])
def test_legacy_external_request_sizes_remain_valid(type_id, size_bytes):
    assert _request_size_contract(type_id, size_bytes, 64)


@pytest.mark.parametrize("type_id", [0, 1, 2, 3, 4, 5])
@pytest.mark.parametrize("size_bytes", [-1, 0, 65])
def test_legacy_external_request_sizes_remain_invalid(type_id, size_bytes):
    assert not _request_size_contract(type_id, size_bytes, 64)


@pytest.mark.parametrize("type_id", [0, 1])
@pytest.mark.parametrize("size_bytes", [1, 64])
def test_generic_dram_preserves_read_write_size_ingress(type_id, size_bytes):
    system = _PuDRoutingSystemUnderTest(num_channels=2)

    routed = system.send_regular_request(type_id, [1], size_bytes)

    assert routed["receiver"] == 1
    assert routed["size_bytes"] == size_bytes


@pytest.mark.parametrize("type_id", [0, 1])
@pytest.mark.parametrize("size_bytes", [-1, 0, 65])
def test_generic_dram_preserves_read_write_size_rejection(type_id, size_bytes):
    system = _PuDRoutingSystemUnderTest(num_channels=1)

    with pytest.raises(RuntimeError, match="must be set by the frontend"):
        system.send_regular_request(type_id, [0], size_bytes)


@pytest.mark.parametrize("size_bytes", [1, 64])
def test_generic_dram_preserves_inherited_pud_size_ingress(size_bytes):
    system = _PuDRoutingSystemUnderTest(num_channels=1)

    routed = system.send_pud_request(REQUEST_TYPE_IDS["RowCopy"], [[0], [0]], size_bytes)

    assert routed["receiver"] == 0


@pytest.mark.parametrize("size_bytes", [-1, 0, 65])
def test_generic_dram_preserves_inherited_pud_size_rejection(size_bytes):
    system = _PuDRoutingSystemUnderTest(num_channels=1)

    with pytest.raises(RuntimeError, match="must be set by the frontend"):
        system.send_pud_request(REQUEST_TYPE_IDS["RowCopy"], [[0], [0]], size_bytes)


def test_internal_direct_command_retains_negative_one_size_default():
    assert _internal_request_default_size() == -1


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
