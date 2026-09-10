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
    ("type_name", "metadata_kind"), [("LC-MOV", "LC"), ("GB-MOV", "GB")]
)
def test_generic_dram_rejects_unlocated_movement_metadata(type_name, metadata_kind):
    dut = make_dut(ramulator.dram.DDR4_PuD_Movement)
    system = _PuDRoutingSystemUnderTest(num_channels=1)
    operands = [operand(dut, row=1), operand(dut, row=2)]

    with pytest.raises(RuntimeError, match="canonical resolved locations"):
        system.send_movement_request(
            REQUEST_TYPE_IDS[type_name], operands, metadata_kind, 1, 2
        )


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
