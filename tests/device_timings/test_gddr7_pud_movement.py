import pytest
from ramulator._ramulator_test import _ComputeRangesUnderTest
from tests.gddr7_pud import dram, resolver, request, timeline
from tests.device_timings.test_pud_compute_ranges import issue


@pytest.mark.parametrize("name,mats", [("LC-MOV", (0, 0)), ("LC-MOV", (15, 16)),
    ("LC-MOV", (0, 31)), ("GB-MOV", (0, 0)), ("GB-MOV", (15, 15)), ("GB-MOV", (30, 30))])
def test_movement_reception_and_local_state(name, mats):
    d, r = _ComputeRangesUnderTest(dram()), resolver()
    i = d.add(request(r, name, mats))
    before = d.shared()[1:]
    for index, t in enumerate(timeline(name)[1]):
        issue(d, i, t)
        assert d.shared()[1:] == before
        if name == "LC-MOV" and index in (1, 2, 3):
            assert d.state(i)["phase"] == "MovementDataValid"
    assert d.state(i)["phase"] == "Recovering"


def test_gb_source_occurrence_is_not_replaced_by_late_destination():
    d, r = _ComputeRangesUnderTest(dram()), resolver()
    i = d.add(request(r, "GB-MOV"))
    issue(d, i, 0)
    issue(d, i, 10, boundary=False)
    issue(d, i, 60)  # Source restoration; destination restoration ends at 70.
    issue(d, i, 70)
    issue(d, i, 101)


def test_movement_column_occupancy_blocks_rck_but_leaves_row_bus_available():
    d, r = _ComputeRangesUnderTest(dram()), resolver()
    i = d.add(request(r, "LC-MOV"))
    issue(d, i, 0)
    issue(d, i, 30)
    assert not d.raw("RCKSTRT", [0, -1, -1, -1], 30)
    assert not d.raw("RCKSTRT", [0, -1, -1, -1], 31)
    assert d.raw("RCKSTRT", [0, -1, -1, -1], 32)
    assert d.raw("ACT", [0, 1, 0, 0], 30, issue=True)


def test_rck_column_occupancy_delays_internal_transfer_exactly():
    d, r = _ComputeRangesUnderTest(dram()), resolver()
    i = d.add(request(r, "LC-MOV"))
    issue(d, i, 0)
    assert d.raw("RCKSTRT", [0, -1, -1, -1], 29, issue=True)
    issue(d, i, 31)
