"""Accepted G6 edges; expected values derived from nominal CK and reception."""
import pytest
import ramulator
from tests.device_timings.harness import DeviceUnderTest

def device():
    return DeviceUnderTest(ramulator.dram.HBM3(
        org_preset="HBM3_8Gb_8hi", timing_preset="HBM3_6400Mbps"))

def addr(command, pc=0, bank=0):
    return [0, pc, -1, -1, -1, -1, -1] if command.endswith("ab") else [0, pc, 0, 0, bank, 0, 0]

EDGES = [
    ("PREab", b, 26) for b in ("REFpb", "RFMpb")
] + [
    (a, b, 416) for a in ("REFab", "RFMab")
    for b in ("REFab", "RFMab", "REFpb", "RFMpb", "PREpb")
] + [
    (a, b, 320) for a in ("REFpb", "RFMpb")
    for b in ("REFab", "RFMab", "PREab", "REFpb", "RFMpb", "PREpb")
]

@pytest.mark.parametrize("before,after,ck", EDGES)
def test_maintenance_recovery_exact_and_pc_scope(before, after, ck):
    d = device()
    d.issue(before, addr(before), 0)
    d.assert_earliest_ready_at(after, addr(after), 2*ck)
    assert d.probe(after, addr(after, pc=1), 1).ready

@pytest.mark.parametrize("before", ["REFpb", "RFMpb"])
@pytest.mark.parametrize("after", ["REFpb", "RFMpb"])
def test_interbank_spacing(before, after):
    d = device()
    d.issue(before, addr(before), 0)
    d.assert_earliest_ready_at(after, addr(after, bank=1), 26)

@pytest.mark.parametrize("ap,nominal", [("RDA", 70), ("WRA", 142)])
@pytest.mark.parametrize("after", ["REFpb", "RFMpb"])
def test_late_ap_drain(ap, nominal, after):
    d = device()
    a = addr(ap)
    d.issue("ACT", a, 0)
    d.issue(ap, a, 200)
    # AP occupancy 2, PB maintenance occupancy 1.
    d.assert_earliest_ready_at(after, a, 200+nominal+2-1)
    assert d.probe(after, addr(after, bank=1), 201).ready

@pytest.mark.parametrize("standard,org,timing,duration", [
    ("HBM3", "HBM3_8Gb_8hi", "HBM3_6400Mbps", 312.5),
    ("HBM4", "HBM4_32Gb_8Hi", "HBM4_8000Mbps", 250),
    ("DDR4", "DDR4_8Gb_x8", "DDR4_2400R", 833),
    ("GDDR7", "GDDR7_16Gb_x8", "GDDR7_28000_PAM3", 571),
])
def test_duration_transport(standard, org, timing, duration):
    dram = getattr(ramulator.dram, standard)(org_preset=org, timing_preset=timing)
    d = DeviceUnderTest(dram)
    assert dram.to_config()["timing"][dram.timing_params.index("tCK_ps")] == duration
    assert d.timings["tCK_ps"] == duration
    assert d._cpp.timing("tCK_ps") == duration
    assert d.time_unit_ns == duration/1000
    assert all(isinstance(v, int) for k,v in d.timings.items() if k != "tCK_ps")
