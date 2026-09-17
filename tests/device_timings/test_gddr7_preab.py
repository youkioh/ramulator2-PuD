"""Exact Accepted G6 repair on conventional and PuD registrations."""
import pytest
import ramulator
from tests.device_timings.harness import DeviceUnderTest


def device(pud):
    cls = ramulator.dram.GDDR7_PuD if pud else ramulator.dram.GDDR7
    return DeviceUnderTest(cls(org_preset="GDDR7_16Gb_x8", timing_preset="GDDR7_28000_PAM3"))


@pytest.mark.parametrize("pud", [False, True])
@pytest.mark.parametrize("bank", [0, 15])
@pytest.mark.parametrize("previous,nominal", [
    ("ACT", 60), ("RD", 4), ("WR", 6+2+30), ("RDA", 4+30), ("WRA", 6+2+30+30),
    ("REFpb", 105), ("RFMpb", 105), ("REFab", 315), ("RFMab", 315),
])
def test_incoming_preab_all_affected_banks(pud, bank, previous, nominal):
    d = device(pud)
    a, all_banks = [0, bank, 0, 0], [0, -1, -1, -1]
    at = 0
    if previous in ("RD", "WR", "RDA", "WRA"):
        d.issue("ACT", a, 0)
        at = 100  # Isolate access/AP recovery from the ACT minimum-active floor.
    d.issue(previous, all_banks if previous.endswith("ab") else a, at)
    occupancy = 2 if previous in ("ACT", "RD", "WR", "RDA", "WRA") else 1
    legal = at + nominal + occupancy - 1
    d.assert_earliest_ready_at("PREab", all_banks, legal)
    d.issue("PREab", all_banks, legal)


@pytest.mark.parametrize("pud", [False, True])
@pytest.mark.parametrize("bank", [0, 15])
@pytest.mark.parametrize("following", ["ACT", "REFpb", "RFMpb", "REFab", "RFMab"])
def test_preab_recovery_covers_every_bank(pud, bank, following):
    d = device(pud)
    d.issue("PREab", [0, -1, -1, -1], 0)
    address = [0, -1, -1, -1] if following.endswith("ab") else [0, bank, 0, 0]
    legal = 30 + 1 - (2 if following == "ACT" else 1)
    d.assert_earliest_ready_at(following, address, legal)
    d.issue(following, address, legal)
