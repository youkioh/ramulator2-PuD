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


def test_internal_direct_command_retains_negative_one_size_default():
    assert _internal_request_default_size() == -1
