import pytest
from ramulator._ramulator_test import _request_type_info
from ramulator.dram.spec import REQUEST_TYPE_IDS, REQUEST_TYPE_NAMES

import ramulator
from tests.controller_scheduling.harness import ControllerUnderTest
from tests.device_timings.harness import DeviceUnderTest


@pytest.mark.parametrize(
    ("type_id", "name", "inherited_pud", "movement", "legacy_stat_slot"),
    [
        (0, "Read", False, False, None),
        (1, "Write", False, False, None),
        (2, "RowCopy", True, False, 0),
        (3, "MAJ3", True, False, 1),
        (4, "MAJ5", True, False, 2),
        (5, "NOT", True, False, 3),
        (6, "LC-MOV", False, True, None),
        (7, "GB-MOV", False, True, None),
    ],
)
def test_request_type_names_and_classification(
    type_id, name, inherited_pud, movement, legacy_stat_slot
):
    info = _request_type_info(type_id)
    assert info == {
        "name": name,
        "inherited_pud": inherited_pud,
        "movement": movement,
        "pud": inherited_pud or movement,
        "controller_sequenced": inherited_pud or movement,
        "legacy_stat_slot": legacy_stat_slot,
    }


@pytest.mark.parametrize("type_id", [-2, -1, 8, 99])
def test_unknown_request_types_fail_classification_and_stat_lookup_safely(type_id):
    assert _request_type_info(type_id) == {
        "name": "Unknown",
        "inherited_pud": False,
        "movement": False,
        "pud": False,
        "controller_sequenced": False,
        "legacy_stat_slot": None,
    }


def test_python_and_cpp_request_ids_have_the_same_stable_order():
    assert tuple(REQUEST_TYPE_IDS) == REQUEST_TYPE_NAMES
    for type_id, name in enumerate(REQUEST_TYPE_NAMES):
        assert REQUEST_TYPE_IDS[name] == type_id
        assert _request_type_info(type_id)["name"] == name


def test_ddr4_rejects_all_pud_and_movement_requests():
    dram = ramulator.dram.DDR4(org_preset="DDR4_8Gb_x8", timing_preset="DDR4_2400R")
    dut = DeviceUnderTest(dram)
    controller = ControllerUnderTest.make_generic_ddr(dram)
    addr_vec = controller.addr_vec(Row=1)
    assert tuple(type(dram).supported_requests) == REQUEST_TYPE_NAMES[:2]
    assert not dut._cpp.supports_inherited_pud_requests()
    assert not dut._cpp.supports_movement_requests()
    for type_id in range(REQUEST_TYPE_IDS["RowCopy"], REQUEST_TYPE_IDS["GB-MOV"] + 1):
        assert not dut._cpp.supports_controller_sequenced_request(type_id)
        with pytest.raises(RuntimeError, match="does not support request type_id"):
            controller._cpp.send_request(type_id, addr_vec)


def test_ddr4_pud_supports_only_the_four_inherited_operations():
    dram = ramulator.dram.DDR4_PuD(org_preset="DDR4_8Gb_x8", timing_preset="DDR4_2400R")
    dut = DeviceUnderTest(dram)
    controller = ControllerUnderTest.make_generic_ddr(dram)
    addr_vec = controller.addr_vec(Row=1)
    assert tuple(type(dram).supported_requests) == REQUEST_TYPE_NAMES[:6]
    assert dut._cpp.supports_inherited_pud_requests()
    assert not dut._cpp.supports_movement_requests()
    for name in ("RowCopy", "MAJ3", "MAJ5", "NOT"):
        assert dut._cpp.supports_controller_sequenced_request(REQUEST_TYPE_IDS[name])
    for name in ("LC-MOV", "GB-MOV"):
        type_id = REQUEST_TYPE_IDS[name]
        assert not dut._cpp.supports_controller_sequenced_request(type_id)
        with pytest.raises(RuntimeError, match="does not support request type_id"):
            controller._cpp.send_request(type_id, addr_vec)


def test_combined_standard_requires_all_inherited_and_movement_mappings():
    dram = ramulator.dram.DDR4_PuD_Movement(
        org_preset="DDR4_8Gb_x8", timing_preset="DDR4_2400R"
    )
    dut = DeviceUnderTest(dram)

    assert tuple(type(dram).supported_requests) == REQUEST_TYPE_NAMES
    assert dut._cpp.supports_inherited_pud_requests()
    assert dut._cpp.supports_movement_requests()
    for type_id in range(REQUEST_TYPE_IDS["RowCopy"], REQUEST_TYPE_IDS["GB-MOV"] + 1):
        assert dut._cpp.supports_controller_sequenced_request(type_id)
