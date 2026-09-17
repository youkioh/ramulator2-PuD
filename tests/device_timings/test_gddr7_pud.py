import pytest
from ramulator._ramulator_test import _ComputeRangesUnderTest
from tests.gddr7_pud import dram, resolver, request, timeline, COMMANDS
from tests.device_timings.test_pud_compute_ranges import issue


@pytest.mark.parametrize("name", list(COMMANDS)[:5])
@pytest.mark.parametrize("mats", [(0, 0), (15, 16), (0, 31)])
def test_compute_exact_reception_boundaries(name, mats):
    d, r = _ComputeRangesUnderTest(dram()), resolver()
    i = d.add(request(r, name, mats))
    _, clocks, _ = timeline(name)
    before = d.shared()[1:]
    for t in clocks:
        issue(d, i, t)
        assert d.shared()[1:] == before
    assert d.state(i)["history"] == clocks
    assert d.state(i)["phase"] == "Recovering"


@pytest.mark.parametrize("destinations", [1, 2, 5, 32])
def test_variable_rowcopy(destinations):
    d, r = _ComputeRangesUnderTest(dram()), resolver()
    i = d.add(request(r, destinations=destinations))
    for t in timeline("RowCopy", destinations)[1]: issue(d, i, t)


@pytest.mark.parametrize("name", ["NOT", "MAJ3", "LC-MOV"])
@pytest.mark.parametrize("previous,bank,ready", [
    ("PREpb", 0, 29), ("PREpb", 1, 1), ("PREab", 0, 29), ("PREab", 1, 29),
    ("REFab", 0, 314), ("REFab", 1, 314),
    ("REFpb", 0, 104), ("REFpb", 1, 20),
    ("RFMab", 0, 314), ("RFMab", 1, 314),
    ("RFMpb", 0, 104), ("RFMpb", 1, 1),
    ("RDA", 0, 134), ("WRA", 0, 168),
])
def test_incoming_conventional_recovery_scopes(name, previous, bank, ready):
    # RFM values verify placeholder plumbing/safety only, not calibrated latency.
    d, r = _ComputeRangesUnderTest(dram()), resolver()
    addr = [0, 0, 0, 0]
    if previous in ("RDA", "WRA"):
        d.raw("ACT", addr, 0, issue=True)
        d.raw(previous, addr, 100, issue=True)
    else:
        d.raw(previous, [0, -1, -1, -1] if previous.endswith("ab") else addr, 0, issue=True)
    i = d.add(request(r, name, bank=bank))
    issue(d, i, ready)


@pytest.mark.parametrize("bank", [0, 1])
def test_invocation_pre_keeps_recovery_local_and_publishes_nppd(bank):
    d, r = _ComputeRangesUnderTest(dram()), resolver()
    first = d.add(request(r))
    second = d.add(request(r, "NOT", mats=(2, 2), bank=bank))
    for t in timeline("RowCopy")[1]: issue(d, first, t)
    terminal = timeline("RowCopy")[1][-1]
    issue(d, second, terminal+1)
    # Separate fresh run isolates PRE spacing from second ACT occupancy.
    d = _ComputeRangesUnderTest(dram())
    first = d.add(request(r))
    for t in timeline("RowCopy")[1]: issue(d, first, t)
    assert not d.raw("PREpb", [0, 1, 0, 0], terminal+1)
    assert d.raw("PREpb", [0, 1, 0, 0], terminal+2)
    # Local PRE must not publish Channel PRE->REFab nRP or sibling nRPD.
    assert d.raw("REFpb", [0, 1, 0, 0], terminal+1)


def test_independent_row_column_bus_and_ordinary_occupancy():
    d, r = _ComputeRangesUnderTest(dram()), resolver()
    d.raw("ACT", [0, 1, 0, 0], 0, issue=True)
    i = d.add(request(r, "NOT"))
    issue(d, i, 2)
    assert not d.raw("ACT", [0, 2, 0, 0], 3)
    assert d.raw("ACT", [0, 2, 0, 0], 4)
    # RCK is a separate two-tick column occupant, irrespective of row issue.
    assert d.raw("RCKSTRT", [0, -1, -1, -1], 2, issue=True)
