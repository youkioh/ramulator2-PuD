import pytest

import ramulator
from ramulator._ramulator_test import _validate_movement_placement
from ramulator.dram.spec import REQUEST_TYPE_IDS
from tests.controller_scheduling.harness import ControllerUnderTest


pytestmark = pytest.mark.controller_scheduling


def make_dram(*, hffs_per_mat=4):
    return ramulator.dram.DDR4_PuD_Movement(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=2,
        hffs_per_mat=hffs_per_mat,
    )


def operands(_dram, **destination_overrides):
    source = [0, 0, 0, 0, 1024, 0]
    destination = dict(
        Channel=0, Rank=0, BankGroup=0, Bank=0, Row=2047, Column=1023
    )
    destination.update(destination_overrides)
    return source, [
        destination[level]
        for level in ("Channel", "Rank", "BankGroup", "Bank", "Row", "Column")
    ]


def validate(dram, type_name, request_operands, first_mat, second_mat):
    return _validate_movement_placement(
        dram.to_config(),
        REQUEST_TYPE_IDS[type_name],
        request_operands,
        "LC" if type_name == "LC-MOV" else "GB",
        first_mat,
        second_mat,
    )


@pytest.mark.parametrize(
    ("mat_begin", "mat_end", "expected_bits"),
    [(0, 0, 4), (7, 23, 68), (0, 127, 512)],
)
def test_lc_accepts_singleton_multi_mat_and_cross_chip_ranges(
    mat_begin, mat_end, expected_bits
):
    dram = make_dram()

    assert validate(dram, "LC-MOV", operands(dram), mat_begin, mat_end) == expected_bits


@pytest.mark.parametrize(("mat_begin", "mat_end"), [(-1, 0), (0, 128), (9, 8)])
def test_lc_rejects_out_of_bounds_or_empty_ranges(mat_begin, mat_end):
    dram = make_dram()

    with pytest.raises(RuntimeError, match="outside|nonempty and ordered"):
        validate(dram, "LC-MOV", operands(dram), mat_begin, mat_end)


@pytest.mark.parametrize(
    ("source_mat", "destination_mat"),
    [(0, 1), (14, 15), (16, 17), (126, 127)],
)
def test_gb_accepts_directed_neighbors_within_one_logical_chip(
    source_mat, destination_mat
):
    dram = make_dram()

    assert validate(dram, "GB-MOV", operands(dram), source_mat, destination_mat) == 4


@pytest.mark.parametrize(
    ("source_mat", "destination_mat", "message"),
    [
        (1, 0, "source plus one"),
        (2, 4, "source plus one"),
        (15, 16, "share a logical chip"),
        (31, 32, "share a logical chip"),
        (-1, 0, "outside"),
        (126, 128, "outside"),
    ],
)
def test_gb_rejects_reverse_non_neighbor_wrap_cross_chip_and_bounds(
    source_mat, destination_mat, message
):
    dram = make_dram()

    with pytest.raises(RuntimeError, match=message):
        validate(dram, "GB-MOV", operands(dram), source_mat, destination_mat)


@pytest.mark.parametrize("type_name", ["LC-MOV", "GB-MOV"])
@pytest.mark.parametrize(
    ("destination_overrides", "message"),
    [
        ({"Rank": 1}, "share Rank"),
        ({"BankGroup": 1}, "share BankGroup"),
        ({"Bank": 1}, "share Bank"),
        ({"Row": 2048}, "share a logical subarray"),
    ],
)
def test_movement_rejects_mismatched_placement_context(
    type_name, destination_overrides, message
):
    dram = make_dram()
    mats = (1, 1) if type_name == "LC-MOV" else (1, 2)

    with pytest.raises(RuntimeError, match=message):
        validate(dram, type_name, operands(dram, **destination_overrides), *mats)


@pytest.mark.parametrize("type_name", ["LC-MOV", "GB-MOV"])
def test_movement_rejects_bad_hierarchy_shape_and_each_non_channel_bound(type_name):
    dram = make_dram()
    source, destination = operands(dram)
    mats = (1, 1) if type_name == "LC-MOV" else (1, 2)

    with pytest.raises(RuntimeError, match="hierarchy coordinates"):
        validate(dram, type_name, [source, destination[:-1]], *mats)

    for level, bound in enumerate((2, 4, 4, 1 << 16, 1024), start=1):
        invalid = destination.copy()
        invalid[level] = bound
        with pytest.raises(RuntimeError, match="outside"):
            validate(dram, type_name, [source, invalid], *mats)

        invalid[level] = -1
        with pytest.raises(RuntimeError, match="outside"):
            validate(dram, type_name, [source, invalid], *mats)


def test_movement_requires_the_controller_owned_channel():
    dram = make_dram()
    request_operands = ([1, 0, 0, 0, 1024, 0], [1, 0, 0, 0, 1025, 0])

    with pytest.raises(RuntimeError, match="controller owns channel 0"):
        validate(dram, "LC-MOV", request_operands, 1, 1)

    assert _validate_movement_placement(
        dram.to_config(),
        REQUEST_TYPE_IDS["LC-MOV"],
        request_operands,
        "LC",
        1,
        1,
        controller_channel_id=1,
    ) == 4


@pytest.mark.parametrize("type_name", ["LC-MOV", "GB-MOV"])
@pytest.mark.parametrize(("source_column", "destination_column"), [(0, 0), (0, 1023), (777, 131)])
def test_movement_columns_are_opaque_with_only_hierarchy_bounds(
    type_name, source_column, destination_column
):
    dram = make_dram()
    source, destination = operands(dram, Column=destination_column)
    source[5] = source_column
    mats = (7, 23) if type_name == "LC-MOV" else (7, 8)

    assert validate(dram, type_name, [source, destination], *mats) > 0


@pytest.mark.parametrize("bad_column", [-1, 1024])
def test_movement_columns_reject_only_values_outside_configured_bound(bad_column):
    dram = make_dram()
    source, destination = operands(dram, Column=bad_column)

    with pytest.raises(RuntimeError, match="Column.*outside"):
        validate(dram, "LC-MOV", [source, destination], 1, 1)


@pytest.mark.parametrize(
    ("type_name", "mats", "hffs_per_mat", "expected_bits"),
    [
        ("LC-MOV", (4, 8), 7, 35),
        ("LC-MOV", (127, 127), 11, 11),
        ("GB-MOV", (4, 5), 7, 7),
        ("GB-MOV", (126, 127), 11, 11),
    ],
)
def test_exact_moved_bits_use_validated_metadata_and_typed_hff_width(
    type_name, mats, hffs_per_mat, expected_bits
):
    dram = make_dram(hffs_per_mat=hffs_per_mat)

    assert validate(dram, type_name, operands(dram), *mats) == expected_bits
