"""Accepted G1 compatibility map, independently derived from byte/bit formulas."""
import itertools
import pytest
import ramulator
from ramulator._ramulator_test import _LocationResolverUnderTest
from tests.unit_tests.test_pud_location import CONTEXT


def resolver():
    return _LocationResolverUnderTest(ramulator.dram.GDDR7(
        org_preset="GDDR7_16Gb_x8", timing_preset="GDDR7_28000_PAM3").to_config(), CONTEXT, {})


def test_page_bijection_and_capacity():
    r = resolver()
    assert r.info["capacity_bytes"] == 512 * 1024**2
    assert (r.info["burst_bytes"], r.info["logical_mats"], r.info["groups"], r.info["hffs"]) == (32, 32, 64, 8)
    seen = set()
    for a, b in itertools.product(range(2048), range(8)):
        bit = r.resolve(a, b)
        expected = [0, 0, 0, 0, 0, a % 32, 8 * (a // 32) + b]
        assert bit["cell"] == expected
        assert bit["external"] == [0, 0, 0, a // 32]
        assert r.inverse(expected) == [a, b]
        seen.add(tuple(expected[-2:]))
    assert len(seen) == 32 * 512


def test_real_hierarchy_and_boundaries():
    r = resolver()
    for bank, row in itertools.product(range(16), [0, 511, 512, 16383]):
        for mat, column in [(0, 0), (31, 511)]:
            a = mat + 32 * (column // 8) + 2048 * bank + 32768 * row
            bit = r.resolve(a, column % 8)
            assert bit["external"] == [0, bank, row, column // 8]
            assert bit["cell"] == [0, bank, row // 512, row % 512, 0, mat, column]
            assert r.inverse(bit["cell"]) == [a, column % 8]
    with pytest.raises(ValueError):
        r.resolve(512 * 1024**2, 0)
    with pytest.raises(ValueError):
        r.footprint("compute", [0, 0, 0, 0, 0])


def test_groups_explicit_placement_and_topology():
    r = resolver()
    for g in range(64):
        cells = r.footprint("group", [0, 15, 512], 0, 31, g)["cells"]
        assert len(cells) == 256
        for mat in range(32):
            assert [c[-1] for c in cells[8*mat:8*mat+8]] == list(range(8*g, 8*g+8))
    assert len(r.footprint("compute_full", [0, 0, 0])["cells"]) == 16384
    for src, dst in itertools.product(range(32), repeat=2):
        assert r.neighbors(src, dst) == (src < 31 and dst == src + 1)


def test_provisional_scalar_map_matches_real_controller_and_channel_mapper():
    from ramulator._ramulator_test import _ChannelMapperUnderTest
    from tests.controller_scheduling.harness import ControllerUnderTest
    r = resolver()
    channel = _ChannelMapperUnderTest({"impl": "CacheLineInterleave"}, 1, 5)
    d = ControllerUnderTest.make_gddr7(ramulator.dram.GDDR7(
        org_preset="GDDR7_16Gb_x8", timing_preset="GDDR7_28000_PAM3"),
        addr_mapper=ramulator.addr_mapper.RoBaRaCoCh())
    for a in [0, 31, 32, 2047, 2048, 32767, 32768, 32768*512, 512*1024**2-1]:
        mapped = channel.apply(a)
        assert mapped["intra_channel_addr"] == a
        assert d._cpp.map_address(a) == r.resolve(a, 0)["external"]


@pytest.mark.parametrize("change", ["rows", "hffs", "width", "hierarchy", "mapper", "topology"])
def test_incompatible_target_profiles_fail_closed(change):
    from tests.gddr7_pud import dram
    cfg, context, overrides = dram(), dict(CONTEXT), {}
    if change == "rows": cfg["org"]["count"][2] *= 2
    elif change == "hffs": cfg["hffs_per_mat"] = 4
    elif change == "width": cfg["channel_width"] = 32
    elif change == "hierarchy": cfg["org"]["count"].append(1)
    elif change == "mapper": context["address_mapper"] = "PassThroughAddrMapper"
    elif change == "topology": overrides["gb_successor"] = list(range(1, 32)) + [0]
    with pytest.raises((ValueError, RuntimeError)):
        _LocationResolverUnderTest(cfg, context, overrides)
