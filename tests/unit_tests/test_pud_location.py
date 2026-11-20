"""W1 value-free geometry tests. No request submission or v2 execution."""

import itertools

import pytest

import ramulator
from ramulator._ramulator_test import _ChannelMapperUnderTest, _LocationResolverUnderTest
from tests.controller_scheduling.harness import ControllerUnderTest


PROFILE = "MIMDRAM-DDR4_8Gb_x8 modeled placement profile v1"
CONTEXT = dict(address_space="physical-test", channels=1,
               channel_mapper="CacheLineInterleave", address_mapper="RoBaRaCoCh",
               row_remapping=False, reserved_rows_per_bank=0)


def dram_config(ranks=1, dram_class=ramulator.dram.DDR4_PuD_Movement, **kwargs):
    return dram_class(org_preset="DDR4_8Gb_x8", timing_preset="DDR4_2400R",
                      rank=ranks, **kwargs).to_config()


def resolver(ranks=1, *, config=None, context=None, profile=None):
    return _LocationResolverUnderTest(config if config is not None else dram_config(ranks),
                                     CONTEXT | (context or {}), profile or {})


def expected(address, bit, ranks):
    offset = address % 64
    burst = address // 64 % 128
    row = address // (131072 * ranks)
    rank = address // 8192 % ranks
    bg = address // (8192 * ranks) % 4
    bank = address // (32768 * ranks) % 4
    external = [0, rank, bg, bank, row, burst]
    cell = [0, rank, bg, bank, row // 1024, row % 1024,
            offset // 8, 2 * (offset % 8) + bit // 4, 4 * burst + bit % 4]
    return external, cell


def base_address(row, ranks):
    channel, rank, bg, bank, full_row = row
    assert channel == 0
    return 8192 * (rank + ranks * (bg + 4 * (bank + 4 * full_row)))


@pytest.mark.parametrize("ranks", [1, 4])
def test_capacity_equations(ranks):
    assert resolver(ranks).info == dict(
        name=PROFILE, capacity_bytes=ranks * 8 * 2**30, rank_row_bits=65536,
        burst_bytes=64, logical_mats=128, groups=128, hffs=4,
        chip_row_bits=8192, chip_burst_bits=64, chip_capacity_bits=8 * 2**30)


@pytest.mark.parametrize("ranks", [1, 4])
def test_full_rank_row_bijection_and_all_ordered_groups(ranks):
    r = resolver(ranks)
    # Only one rank-row's identity set is allocated, never full DRAM contents.
    seen = set()
    for address in range(8192):
        for bit in range(8):
            result = r.resolve(address, bit)
            ext, cell = expected(address, bit, ranks)
            assert result["external"] == ext
            assert result["cell"] == cell
            assert result["origin"] == [address, bit]
            assert result["group"] == address // 64
            assert result["hff"] == bit % 4
            assert r.inverse(cell) == [address, bit]
            seen.add(tuple(cell[6:]))
    assert seen == set(itertools.product(range(8), range(16), range(512)))
    for group in range(128):
        cells = r.footprint("group", [0, 0, 0, 0, 0], 0, 127, group)["cells"]
        assert len(cells) == 512
        for mat in range(128):
            assert [c[8] for c in cells[4 * mat:4 * mat + 4]] == list(range(4 * group, 4 * group + 4))
            assert all(c[6:8] == [mat // 16, mat % 16] for c in cells[4 * mat:4 * mat + 4])


@pytest.mark.parametrize("ranks", [1, 4])
def test_rank_bank_and_row_subarray_boundaries(ranks):
    r = resolver(ranks)
    for rank, bg, bank, row in itertools.product(range(ranks), range(4), range(4),
                                                 [0, 1, 1023, 1024, 1025, 64511, 64512, 65535]):
        base = base_address([0, rank, bg, bank, row], ranks)
        for offset in [0, 7, 8, 63, 64, 8191]:
            for bit in [0, 3, 4, 7]:
                address = base + offset
                result = r.resolve(address, bit)
                ext, cell = expected(address, bit, ranks)
                assert result["external"] == ext
                assert result["cell"] == cell
                assert r.inverse(cell) == [address, bit]
    # Last valid bit, plus transitions between adjacent external contexts.
    capacity = r.info["capacity_bytes"]
    assert r.resolve(capacity - 1, 7)["cell"] == [0, ranks - 1, 3, 3, 63, 1023, 7, 15, 511]
    for boundary in [8192, 8192 * ranks, 32768 * ranks, 131072 * ranks, 131072 * ranks * 1024]:
        for address in [boundary - 1, boundary]:
            assert r.resolve(address, 7)["external"] == expected(address, 7, ranks)[0]


@pytest.mark.parametrize("dram_class", [ramulator.dram.DDR4, ramulator.dram.DDR4_PuD,
                                        ramulator.dram.DDR4_PuD_Movement])
@pytest.mark.parametrize("ranks", [1, 4])
def test_matches_existing_channel_and_controller_mappers(dram_class, ranks):
    dram = dram_class(org_preset="DDR4_8Gb_x8", timing_preset="DDR4_2400R", rank=ranks)
    r = resolver(config=dram.to_config())
    channel = _ChannelMapperUnderTest({"impl": "CacheLineInterleave"}, 1, 6)
    controller = ControllerUnderTest.make_generic_ddr(dram, addr_mapper=ramulator.addr_mapper.RoBaRaCoCh())
    for address in [0, 1, 7, 8, 63, 64, 8191, 8192, 8192 * ranks,
                    32768 * ranks, 131072 * ranks, 131072 * ranks * 1024,
                    r.info["capacity_bytes"] - 1]:
        mapped = channel.apply(address)
        assert mapped["intra_channel_addr"] == address
        assert controller._cpp.map_address(mapped["intra_channel_addr"]) == r.resolve(address, 0)["external"]


@pytest.mark.parametrize("ranks", [1, 4])
def test_scalar_domain_rejection_without_wrapping(ranks):
    r = resolver(ranks)
    for address, bit in [(-1, 0), (-(2**63), 0), (r.info["capacity_bytes"], 0),
                         (2**63 - 1, 7), (0, -1), (0, 8)]:
        with pytest.raises(ValueError, match="out of bounds"):
            r.resolve(address, bit)


@pytest.mark.parametrize("index,upper", list(enumerate([1, 4, 4, 4, 64, 1024, 8, 16, 512])))
def test_all_cell_coordinate_bounds(index, upper):
    r = resolver(4)
    for value in [-1, upper]:
        cell = [0] * 9
        cell[index] = value
        with pytest.raises(ValueError, match="out of bounds"):
            r.inverse(cell)


@pytest.mark.parametrize("index,upper", list(enumerate([1, 4, 4, 4, 65536])))
def test_external_row_coordinate_bounds(index, upper):
    r = resolver(4)
    for value in [-1, upper]:
        row = [0] * 5
        row[index] = value
        with pytest.raises(ValueError, match="out of bounds"):
            r.footprint("act", row)


@pytest.mark.parametrize("kind,coordinates,first,last,selector", [
    ("group", [0]*5, -1, 0, 0), ("group", [0]*5, 0, 128, 0),
    ("compute", [0]*5, 2, 1, None), ("group", [0]*5, 0, 0, -1),
    ("group", [0]*5, 0, 0, 128), ("burst", [0]*5, 0, 0, -1),
    ("burst", [0]*5, 0, 0, 128), ("group", [0]*5, 0, 0, None),
    ("layout", [0, 0, 0, 0, 64, 0], 0, 0, None),
    ("layout", [0, 0, 0, 0, 0, 1024], 0, 0, None),
])
def test_region_bounds(kind, coordinates, first, last, selector):
    with pytest.raises(ValueError):
        resolver().footprint(kind, coordinates, first, last, selector)


def test_region_identity_association_and_index_validation():
    r = resolver()
    for index in [-1, 512]:
        with pytest.raises(ValueError, match="index out of bounds"):
            r.region_cell(index)
    with pytest.raises(ValueError, match="foreign profile/routing"):
        r.region_cell(0, foreign=True)
    with pytest.raises(ValueError, match="inconsistent resolved region"):
        r.region_cell(0, tampered=True)
    assert r.resolve(7, 4)["profile"] == PROFILE
    assert r.resolve(7, 4)["address_space"] == CONTEXT["address_space"]


def test_value_free_footprints_and_explicit_layout_union():
    r = resolver()
    row = [0, 0, 2, 3, 1024]
    act = r.footprint("act", row)
    assert len(act["cells"]) == 65536 and act["burst"] is None
    compute = r.footprint("compute", row, 15, 16)
    layout = r.footprint("layout", [0, 0, 2, 3, 1, 0], 15, 16)
    assert compute == layout
    assert len(compute["cells"]) == 1024 and compute["burst"] is None
    assert compute["external_row"] == row
    burst = r.footprint("burst", row, selector=127)
    assert len(burst["cells"]) == 512
    assert burst["burst"] == 127
    selected = r.footprint("group", row, 15, 16, 127)
    assert selected["cells"] == burst["cells"][60:68]
    assert set(map(tuple, compute["cells"])) <= set(map(tuple, act["cells"]))
    assert set(map(tuple, selected["cells"])) <= set(map(tuple, compute["cells"]))
    # Whole mat-row origins are discontiguous physical unions, not scalar spans.
    physical = [r.inverse(c) for c in r.footprint("compute", row, 0, 0)["cells"]]
    assert physical[4][0] - physical[0][0] == 64
    assert physical[0][0] == base_address(row, 1)


def test_directed_local_topology_and_ordered_movement_endpoints():
    r = resolver()
    for source, destination in [(0, 1), (14, 15), (16, 17), (126, 127)]:
        assert r.neighbors(source, destination)
        src = r.footprint("group", [0, 0, 0, 0, 0], source, source, 0)["cells"]
        dst = r.footprint("group", [0, 0, 0, 0, 1023], destination, destination, 127)["cells"]
        assert len(src) == len(dst) == 4
        for h, (s, d) in enumerate(zip(src, dst)):
            assert r.resolve(*r.inverse(s))["hff"] == r.resolve(*r.inverse(d))["hff"] == h
    for pair in [(1, 0), (15, 16), (127, 0), (0, 2), (0, 0)]:
        assert not r.neighbors(*pair)
    for pair in [(-1, 0), (0, 128)]:
        with pytest.raises(ValueError):
            r.neighbors(*pair)


def test_synthetic_coherent_replacement_with_nonidentity_groups_and_positions():
    # Software fixture only: coordinated 8 mats/chip, 1024 cells/mat-row,
    # 8 positions/group plus nonidentity G/B, lane, and position permutations.
    successors = [m + 1 if m % 8 != 7 else -1 for m in range(64)]
    successors[0] = 2  # Test-only wiring; numeric adjacency must not decide GB legality.
    profile = dict(name="synthetic coherent test profile", mats_per_chip=8,
                   cells_per_mat_row=1024, hffs_per_mat=8,
                   gb_successor=successors,
                   burst_to_group=[(17*b + 3) % 128 for b in range(128)],
                   bit_to_slot=[(b + 8) % 512 for b in range(512)],
                   group_position_to_column=[8*g + 7-h for g in range(128) for h in range(8)])
    r = resolver(config=dram_config(hffs_per_mat=8), profile=profile)
    assert r.info["logical_mats"] == 64 and r.info["hffs"] == 8
    assert r.info["rank_row_bits"] == 65536 and r.info["capacity_bytes"] == 8 * 2**30
    seen = set()
    for address in range(8192):
        for bit in range(8):
            result = r.resolve(address, bit)
            slot = (8 * (address % 64) + bit + 8) % 512
            group = (17 * (address // 64) + 3) % 128
            assert result["group"] == group
            assert result["cell"][6:] == [slot // 64, slot // 8 % 8, 8 * group + 7 - slot % 8]
            assert result["external"][5] == address // 64
            assert r.inverse(result["cell"]) == [address, bit]
            seen.add(tuple(result["cell"][6:]))
    assert seen == set(itertools.product(range(8), range(8), range(1024)))
    for burst in range(128):
        group = (17 * burst + 3) % 128
        ordinary = r.footprint("burst", [0]*5, selector=burst)
        selected = r.footprint("group", [0]*5, 7, 8, group)
        assert selected["burst"] == burst
        assert selected["cells"] == ordinary["cells"][56:72]
        for h, cell in enumerate(selected["cells"]):
            assert r.resolve(*r.inverse(cell))["hff"] == h % 8
    assert not r.neighbors(7, 8) and r.neighbors(8, 9)
    assert r.neighbors(0, 2) and not r.neighbors(0, 1)
    assert not r.neighbors(2, 0)
    assert r.segments(7, 8) == [[0, 7, 7], [1, 0, 0]]
    assert r.segments(0, 63) == [[chip, 0, 7] for chip in range(8)]
    assert len(r.footprint("compute", [0]*5, 0, 0)["cells"]) == 1024


@pytest.mark.parametrize("context", [dict(channels=0), dict(channels=3),
    dict(channel_mapper="PassThroughChannelMapper"), dict(address_mapper="PassThroughAddrMapper"),
    dict(address_mapper="ChRaBaRoCo"), dict(address_mapper="RITAddrMapper"),
    dict(row_remapping=True), dict(reserved_rows_per_bank=1), dict(reserved_rows_per_bank=-1),
    dict(address_space="")])
def test_unsupported_v2_mapping_context(context):
    with pytest.raises(ValueError):
        resolver(context=context)


@pytest.mark.parametrize("field", ["dq", "prefetch", "channel_width", "organization_columns",
    "bank_groups", "banks_per_group", "rows_per_bank", "chips", "mats_per_chip",
    "cells_per_mat_row", "hffs_per_mat", "rows_per_subarray"])
@pytest.mark.parametrize("value", [0, -1])
def test_positive_profile_dimensions(field, value):
    with pytest.raises(ValueError, match="positive"):
        resolver(profile={field: value})


@pytest.mark.parametrize("profile", [dict(hffs_per_mat=3), dict(rows_per_subarray=1000),
    dict(organization_columns=1023), dict(cells_per_mat_row=516), dict(mats_per_chip=8),
    dict(prefetch=16), dict(chips=4), dict(rank_counts=[]), dict(rank_counts=[0]),
    dict(rank_counts=[3]), dict(name=""), dict(burst_to_group=[0]*128),
    dict(burst_to_group=list(range(127))), dict(bit_to_slot=[0]*512),
    dict(group_position_to_column=[0]*512), dict(bit_to_slot=list(range(1, 513))),
    dict(group_position_to_column=[-1] + list(range(1, 512)))])
def test_incoherent_profile_rejected(profile):
    with pytest.raises(ValueError):
        resolver(profile=profile)


@pytest.mark.parametrize("ranks", [2, 8])
def test_initial_profile_unsupported_rank_replication(ranks):
    with pytest.raises(ValueError, match="rank replication"):
        resolver(ranks)


@pytest.mark.parametrize("change", ["dq", "width", "columns", "rows", "subdivision", "payload"])
def test_actual_spec_must_match_profile(change):
    config = dram_config()
    if change == "dq": config["org"]["dq"] = 4
    elif change == "width": config["channel_width"] = 32
    elif change == "columns": config["org"]["count"][5] = 2048
    elif change == "rows": config["org"]["count"][4] = 32768
    elif change == "subdivision": config["geometry"]["rows_per_subarray"] = 512
    elif change == "payload": config["data_payload_bytes"] = 32
    with pytest.raises(ValueError, match="mismatch"):
        resolver(config=config)


def test_inconsistent_hff_override_is_v2_only_rejection():
    from ramulator._ramulator_test import _DeviceUnderTest
    config = dram_config(hffs_per_mat=7)
    assert _DeviceUnderTest(config).hffs_per_mat == 7
    with pytest.raises(ValueError, match="HFF-only override"):
        resolver(config=config)


def test_capacity_overflow_rejected_before_allocation():
    config = dram_config()
    config["org"]["count"][2:5] = [2**30, 2**30, 2**30]
    with pytest.raises(ValueError, match="capacity overflow"):
        resolver(config=config, profile=dict(bank_groups=2**30, banks_per_group=2**30, rows_per_bank=2**30))


def test_initial_gb_topology_all_direct_pairs():
    r = resolver()
    for source, destination in itertools.product(range(128), repeat=2):
        assert r.neighbors(source, destination) == (
            source % 16 != 15 and destination == source + 1)


@pytest.mark.parametrize("size", [0, 127, 129])
def test_gb_successor_table_size(size):
    with pytest.raises(ValueError, match="GB successor table size mismatch"):
        resolver(profile=dict(gb_successor=[-1] * size))


@pytest.mark.parametrize("target", [-2, 128])
def test_gb_successor_target_bounds(target):
    table = [-1] * 128
    table[0] = target
    with pytest.raises(ValueError, match="GB successor target out of bounds"):
        resolver(profile=dict(name="synthetic topology bounds fixture", gb_successor=table))


@pytest.mark.parametrize("source,target", [(15, 16), (15, 0), (127, 0), (0, 2), (1, 0), (0, -1)])
def test_initial_profile_rejects_changed_gb_topology(source, target):
    table = [m + 1 if m % 16 != 15 else -1 for m in range(128)]
    table[source] = target
    with pytest.raises(ValueError, match="initial profile requires same-chip forward GB topology without wrap"):
        resolver(profile=dict(gb_successor=table))


@pytest.mark.parametrize("first,last,expected", [
    (0, 0, [[0, 0, 0]]), (127, 127, [[7, 15, 15]]),
    (3, 10, [[0, 3, 10]]), (16, 31, [[1, 0, 15]]),
    (15, 16, [[0, 15, 15], [1, 0, 0]]),
    (14, 34, [[0, 14, 15], [1, 0, 15], [2, 0, 2]]),
    (0, 127, [[chip, 0, 15] for chip in range(8)]),
])
def test_range_segmentation(first, last, expected):
    r = resolver()
    segments = r.segments(first, last)
    assert segments == expected
    # Compare segment identities to canonical region cells, with no consumer
    # reconstruction of chip/local-mat identity from logical-mat arithmetic.
    cells = r.footprint("group", [0] * 5, first, last, 0)["cells"]
    assert [(c[6], c[7]) for c in cells[::4]] == [
        (chip, mat) for chip, lo, hi in segments for mat in range(lo, hi + 1)]


@pytest.mark.parametrize("first,last", [(-1, 0), (0, -1), (128, 128), (0, 128), (3, 2)])
def test_range_segmentation_rejects_invalid_ranges(first, last):
    with pytest.raises(ValueError):
        resolver().segments(first, last)
