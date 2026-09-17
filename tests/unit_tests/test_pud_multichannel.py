"""Global system identity and unchanged local scalar mapper composition."""
import pytest
from ramulator._ramulator_test import _LocationResolverUnderTest, _LocatedSystemUnderTest, _located_request
from ramulator.dram.spec import REQUEST_TYPE_IDS
from tests import gddr7_pud, hbm3_pud
from tests.unit_tests.test_pud_location import CONTEXT, resolver as ddr4_resolver
from tests.unit_tests.test_pud_request_locations import controller as ddr4_controller


def fixture(target):
    if target == "DDR4":
        config = ddr4_controller()
        config["pud_placement_profile"] = "MIMDRAM_DDR4_8Gb_x8_v1"
        return config, ddr4_resolver(), 1
    module, count = (gddr7_pud, 4) if target == "GDDR7" else (hbm3_pud, 16)
    return module.controller_config(), module.resolver(), count


@pytest.mark.parametrize("target", ["DDR4", "GDDR7", "HBM3"])
def test_system_association_and_explicit_routing(target):
    config, local, count = fixture(target)
    system = _LocatedSystemUnderTest(config, local, install=False, channels=count)
    info = system.channel_info()
    assert [r["id"] for r in info] == list(range(count))
    assert all(r["local_channels"] == 1 and r["shared"] and r["bank_sizes"][0] == count for r in info)
    depth = len(info[0]["bank_sizes"])
    for channel in range(count):
        row = [channel] + [0]*(depth-1) + [10]
        desc = [dict(kind="compute", row=row, range=[0, 0])]
        request = system.request(REQUEST_TYPE_IDS["NOT"], desc, 64 if target == "DDR4" else 32)
        assert system.submit(request, channel)
    system.advance(400)
    assert len(system.completions()) == count
    assert sorted(r["source_id"] for r in system.completions()) == list(range(count))
    # The fixture's direct controller path selects the last controller.
    if count > 1:
        request = system.request(REQUEST_TYPE_IDS["NOT"],
            [dict(kind="compute", row=[0]*depth+[12], range=[1, 1])], 32)
        with pytest.raises(RuntimeError, match="controller channel"):
            system.send(request, "controller")
    foreign = _located_request(local, REQUEST_TYPE_IDS["NOT"],
        [dict(kind="compute", row=[0]*depth+[12], range=[1, 1])], 64 if target == "DDR4" else 32)
    with pytest.raises(RuntimeError, match="association"):
        system.send(foreign)
    system.finalize()


@pytest.mark.parametrize("target", ["GDDR7", "HBM3"])
def test_scalar_channel_compaction_and_inverse(target):
    config, local, count = fixture(target)
    resolver = _LocationResolverUnderTest(config["dram"], dict(CONTEXT, channels=count))
    system = _LocatedSystemUnderTest(config, local, install=False, channels=count)
    for compact in (0, 31, 32, 2048, 65536, local.info["capacity_bytes"]-1):
        for channel in range(count):
            address = (compact//32*count+channel)*32+compact%32
            result = resolver.resolve(address, 7)
            assert result["external"] == [channel, *local.resolve(compact, 7)["external"][1:]]
            assert resolver.inverse(result["cell"]) == [address, 7]
            observed = system.ordinary(address, REQUEST_TYPE_IDS["Read"], cells=False)
            assert observed["accepted"] and observed["external"] == result["external"]
    system.finalize()


@pytest.mark.parametrize("target", ["GDDR7", "HBM3"])
def test_cross_channel_and_unsupported_interleave(target):
    config, local, count = fixture(target)
    system = _LocatedSystemUnderTest(config, local, install=False, channels=count)
    depth = len(system.channel_info()[0]["bank_sizes"])
    desc = [dict(kind="compute", row=[c]+[0]*(depth-1)+[10+c], range=[0, 0]) for c in (0, 1)]
    with pytest.raises((RuntimeError, ValueError)):
        system.send(system.request(REQUEST_TYPE_IDS["RowCopy"], desc, 32))
    with pytest.raises(ValueError, match="mapper"):
        _LocationResolverUnderTest(config["dram"], dict(CONTEXT, channels=count, interleave_bits=1))
    system.finalize()
