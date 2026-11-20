"""Physical-resource exclusion through the canonical public execution path."""
import itertools

import pytest

from ramulator.dram.spec import REQUEST_TYPE_IDS
from tests.controller_scheduling.GenericDDRController.test_pud_public import system, events, times
from tests.unit_tests.test_pud_request_locations import descriptor

KINDS = ("RowCopy", "LC-MOV", "GB-MOV")
TIMES = {"RowCopy": [0, 40, 45], "LC-MOV": [0, 16, 39, 55, 94, 114],
         "GB-MOV": [0, 1, 39, 41, 59]}
TOTAL = {"RowCopy": 61, "LC-MOV": 130, "GB-MOV": 75}


def req(d, kind, mats=(0, 1), row=10):
    ranges = [(mats[0], mats[0]), (mats[1], mats[1])] if kind == "GB-MOV" else [mats]*2
    return d.request(REQUEST_TYPE_IDS[kind],
                     [descriptor(row+i, selected, None if kind == "RowCopy" else i+3)
                      for i, selected in enumerate(ranges)], 64 if kind == "RowCopy" else -1)


@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
@pytest.mark.parametrize("first,second", list(itertools.product(KINDS, repeat=2)))
@pytest.mark.parametrize("intersect", [False, True])
def test_all_pair_classes_actual_execution_and_recovery(scheduler, first, second, intersect):
    d = system(scheduler)
    assert d.submit(req(d, first), 0)
    # Intersect at mat 1: for GB this is A's destination and B's source.
    assert d.submit(req(d, second, (1, 2) if intersect else (2, 3), row=30), 1)
    d.advance(400)
    a, b = times(d, 0), times(d, 1)
    done = {e["source_id"]: e for e in d.completions()}
    assert len(done) == len(d.completions()) == 2
    if intersect:
        # Compute preallocation can precede movement's first-ACT acquisition.
        earlier, later = (0, 1) if a[0] < b[0] else (1, 0)
        assert times(d, later)[0] >= done[earlier]["depart"]
    else:
        # Both issue real commands before either sequence closes, not just enqueue.
        assert max(a[0], b[0]) < min(a[-1], b[-1])
    assert len({e["clk"] for e in d.issued()}) == len(d.issued())
    for source, kind in enumerate((first, second)):
        trace = events(d, source)
        expected = ({"RowCopy": ["ACT_PUD_S_OC", "ACT_PUD", "PREpb"],
                     "LC-MOV": ["ACT_MOV", "RD_MOV", "PREpb", "ACT_MOV", "WR_MOV", "PREpb"],
                     "GB-MOV": ["ACT_MOV", "ACT_MOV", "RD_MOV", "WR_MOV", "PREpb"]})[kind]
        assert [e["command"] for e in trace] == expected
        assert done[source]["depart"] == trace[-1]["clk"] + 16
        assert done[source]["depart"] >= trace[0]["clk"] + TOTAL[kind]
    stats = d.stats()["controller"]
    for kind in set((first, second)):
        key = kind.lower().replace("-", "")
        count = (first, second).count(kind)
        assert stats[f"num_pud_{key}_reqs"] == stats[f"num_pud_{key}_reqs_completed"] == count
    assert d.scheduling()["held"] == 0


@pytest.mark.parametrize("first,second", list(itertools.product(KINDS, repeat=2)))
def test_same_bank_different_subarray_still_serializes(first, second):
    d = system()
    assert d.submit(req(d, first), 0)
    d.advance(1)  # Ensure movement has acquired its footprint before the next arrival.
    assert d.submit(req(d, second, (2, 3), row=1034), 1)
    d.advance(400)
    assert times(d, 1)[0] >= next(e["depart"] for e in d.completions() if e["source_id"] == 0)


@pytest.mark.parametrize("kind", KINDS)
def test_lc_source_close_and_terminal_recovery_leave_other_context_intact(kind):
    d = system()
    assert d.submit(req(d, "LC-MOV", (15, 16)), 0)  # Cross-chip LC union.
    d.advance(38)
    assert d.submit(req(d, kind, (17, 18), row=40), 1)
    d.advance(300)
    assert times(d, 0) == [t+1 for t in TIMES["LC-MOV"]]
    b = times(d, 1)
    assert b[0] < 40 < b[-1]  # A's source PRE occurs while B is executing.
    expected = [0, 2, 39, 41, 59] if kind == "GB-MOV" else TIMES[kind]
    assert [t-b[0] for t in b] == expected  # Shared issue delays the second GB ACT.
    assert len(d.completions()) == 2 and d.scheduling()["held"] == 0


@pytest.mark.parametrize("kind", ["LC-MOV", "GB-MOV"])
def test_movement_and_compute_overlap_while_conflicting_movement_retries(kind):
    d = system()
    assert d.submit(req(d, kind), 0)
    d.advance(1)
    assert d.submit(req(d, "RowCopy", (2, 3)), 1)
    assert d.submit(req(d, kind, (1, 2)), 2)
    d.advance(3)
    assert times(d, 1) == [3 if kind == "GB-MOV" else 2]
    pending = next(r for r in d.scheduling()["pending"] if r["source_id"] == 2)
    assert pending["history"] == [-1]*len(TIMES[kind])
    assert pending["phase"] == -1
    assert d.scheduling()["held"] == 2  # Only the first movement and compute.
    assert times(d, 2) == []
    d.advance(400)
    assert times(d, 2)[0] >= TOTAL[kind]+1
    assert len(d.completions()) == 3 and d.scheduling()["held"] == 0
