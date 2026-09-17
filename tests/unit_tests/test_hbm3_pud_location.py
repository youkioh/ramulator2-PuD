"""HBM3 G1 placement oracle, derived from the Accepted hierarchy/bit map."""
import itertools
import pytest
import ramulator
from ramulator._ramulator_test import _LocationResolverUnderTest, _ChannelMapperUnderTest
from tests.unit_tests.test_pud_location import CONTEXT

def config():
    return ramulator.dram.HBM3(org_preset="HBM3_8Gb_8hi", timing_preset="HBM3_6400Mbps").to_config()

def resolver():
    return _LocationResolverUnderTest(config(), CONTEXT, {})

def test_page_bijection():
    r = resolver()
    assert r.info["capacity_bytes"] == 512*1024**2
    assert [r.info[k] for k in ("burst_bytes", "logical_mats", "groups", "hffs")] == [32,16,32,16]
    seen = set()
    for a,b in itertools.product(range(1024), range(8)):
        slot = 8*(a%32)+b
        cell = [0,0,0,0,0,0,0,0,slot//16,16*(a//32)+slot%16]
        result = r.resolve(a,b)
        assert result["cell"] == cell
        assert result["external"] == [0,0,0,0,0,0,a//32]
        assert r.inverse(cell) == [a,b]
        seen.add(tuple(cell))
    assert len(seen) == 8192

def test_hierarchy_boundaries_and_controller_map():
    from tests.controller_scheduling.harness import ControllerUnderTest
    d = ControllerUnderTest.make_hbm34(ramulator.dram.HBM3(
        org_preset="HBM3_8Gb_8hi", timing_preset="HBM3_6400Mbps"),
        addr_mapper=ramulator.addr_mapper.RoBaRaCoCh())
    r = resolver()
    channel = _ChannelMapperUnderTest({"impl":"CacheLineInterleave"},1,5)
    for pc,sid,bg,bank,row in itertools.product(range(2),range(2),range(4),range(4),[0,511,512,8191]):
        for mat,col in [(0,0),(15,511)]:
            a = 65536*row+16384*bank+4096*bg+2048*sid+1024*pc+32*(col//16)+2*mat+(col%16)//8
            bit = col%8
            expected = [0,pc,sid,bg,bank,row//512,row%512,0,mat,col]
            result = r.resolve(a,bit)
            assert result["cell"] == expected
            assert r.inverse(expected) == [a,bit]
            assert channel.apply(a)["intra_channel_addr"] == a
            assert d._cpp.map_address(a) == result["external"]

def test_explicit_groups_and_topology_without_pa():
    r = resolver()
    for g in range(32):
        cells = r.footprint("group",[0,1,1,3,3,512],0,15,g)["cells"]
        assert len(cells) == 256
        for m in range(16):
            assert cells[m*16:(m+1)*16] == [
                [0,1,1,3,3,1,0,0,m,g*16+h] for h in range(16)]
    assert len(r.footprint("compute_full",[0,1,1,3,3,511])["cells"]) == 8192
    for a,b in itertools.product(range(16),repeat=2):
        assert r.neighbors(a,b) == (a<15 and b==a+1)

@pytest.mark.parametrize("change",["pc","sid","bg","bank","row","column","width","hierarchy","rank","profile_pc","profile_sid","topology","mapper"])
def test_reject_invalid_organization(change):
    cfg, ctx, overrides = config(),dict(CONTEXT),{}
    if change in ("pc","sid","bg","bank","row","column"):
        cfg["org"]["count"][("pc","sid","bg","bank","row","column").index(change)+1] *= 2
    elif change == "width": cfg["channel_width"] = 64
    elif change == "hierarchy": cfg["org"]["count"].append(1)
    elif change == "rank": overrides["rank_counts"] = [1]
    elif change == "profile_pc": overrides["pseudochannels"] = 0
    elif change == "profile_sid": overrides["sids_per_pc"] = 3
    elif change == "topology": overrides["gb_successor"] = list(range(1,16))+[0]
    elif change == "mapper": ctx["address_mapper"] = "PassThroughAddrMapper"
    with pytest.raises((ValueError,RuntimeError)):
        _LocationResolverUnderTest(cfg,ctx,overrides)

@pytest.mark.parametrize("row",[[0,2,0,0,0,0],[0,0,2,0,0,0],[0,0,0,4,0,0],[0,0,0,0,4,0],[0,0,0,0,0,8192],[0,0,0,0,0]])
def test_invalid_explicit_hierarchy(row):
    with pytest.raises((ValueError,RuntimeError)):
        resolver().footprint("compute",row,0,0)

def test_capacity_and_mat_bounds():
    r = resolver()
    with pytest.raises(ValueError): r.resolve(512*1024**2,0)
    with pytest.raises(ValueError): r.footprint("compute",[0,0,0,0,0,0],0,16)
