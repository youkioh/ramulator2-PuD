"""W4 protected lifetime using explicit reservations, without W5-W7 scheduling."""

import pytest

from ramulator._ramulator_test import _ComputeLifecycleUnderTest
from tests.device_timings.test_pud_compute_ranges import TIMELINES, TOTALS
from tests.unit_tests.test_pud_location import resolver
from tests.unit_tests.test_pud_request_locations import COMPUTE, controller, descriptor, request


def fixture():
    return _ComputeLifecycleUnderTest(controller(mapper="PassThroughAddrMapper")), resolver()


def compute(r, name="RowCopy", mats=(15, 16), row=10, bank=0):
    operands = [descriptor(row+i, mats) for i in range(COMPUTE[name])]
    for operand in operands:
        operand["row"][3] = bank
    return request(r, name, operands)


def drained(d):
    s = d.snapshot()
    assert s["held"] == []
    assert s["pending"] == s["active"] == s["delayed"] == s["rw_buffered"] == 0
    assert not any(s["active_per_bank"])


@pytest.mark.parametrize("name", COMPUTE)
@pytest.mark.parametrize("mats", [(0, 0), (15, 16), (0, 127)])
def test_terminal_retirement_preserves_protection_until_recovery(name, mats):
    d, r = fixture()
    a = compute(r, name, mats)
    overlap = compute(r, name, mats, row=100)  # Row cells differ; mat resources do not.
    assert d.add(a.copy(), 1)
    assert d.snapshot()["held"] == []  # Pending, unallocated requests own nothing.
    assert d.reserve(1, 0)
    stale = d.save(1)
    assert not d.saved_expired(stale)
    initial = d.snapshot()
    assert initial["active"] == 0 and not any(initial["active_per_bank"])
    assert initial["held"][0]["phase"] == 0  # Pre-first-ACT Closed, but reserved.
    assert not d.available(overlap, 1)
    assert not d.available(compute(r, bank=1), 0)
    with pytest.raises(RuntimeError, match="already has"):
        d.reserve(1, 1)
    with pytest.raises(RuntimeError, match="terminal PRE"):
        d.retire_copy(1)
    assert d.snapshot() == initial

    for index, clk in enumerate(TIMELINES[name]):
        d.dispatch(1, clk)
        if index == 0:
            assert d.snapshot()["active"] == 1
    terminal, ready = TIMELINES[name][-1], TOTALS[name]
    for clk in [terminal, ready - 1]:
        d.advance(clk)
        s = d.snapshot()
        assert s["pending"] == s["active"] == 0 and not any(s["active_per_bank"])
        assert s["delayed"] == 1
        assert s["held"] == [dict(engine=0, phase=3, depart=ready,
                                  completion_pending=True)]
        assert not d.available(overlap, 1) and not d.available(compute(r, bank=1), 0)
        assert d.completions() == []
        assert s["counters"][f"num_pud_{name.lower()}_reqs_completed"] == 0
        with pytest.raises(RuntimeError, match="not schedulable"):
            d.dispatch(1, clk)
        with pytest.raises(RuntimeError, match="terminal PRE"):
            d.retire_copy(1)  # A copied Request cannot retire the same context twice.
        assert d.snapshot() == s

    d.advance(ready)
    assert d.available(overlap, 0)
    assert d.saved_expired(stale)
    with pytest.raises(RuntimeError, match="stale compute reservation"):
        d.reserve_saved(stale, 0)
    with pytest.raises(RuntimeError, match="stale protected"):
        d.stale_dispatch(stale)
    event, = d.completions()
    assert event["depart"] == event["callback_clk"] == ready
    assert event["context_expired"]
    assert event["history"] == TIMELINES[name]
    assert event["cursor"] == len(TIMELINES[name])
    assert event["stats"]["held"] == [] and event["stats"]["delayed"] == 0
    counters = event["stats"]["counters"]
    assert counters[f"num_pud_{name.lower()}_reqs"] == 1
    assert counters[f"num_pud_{name.lower()}_reqs_completed"] == 1
    assert counters[f"pud_{name.lower()}_latency"] == ready
    assert counters[f"avg_pud_{name.lower()}_latency"] == ready
    assert counters["num_read_reqs"] == counters["num_write_reqs"] == 0
    d.advance(ready + 100)
    assert len(d.completions()) == 1
    assert d.snapshot()["counters"][f"num_pud_{name.lower()}_reqs_completed"] == 1
    drained(d)


@pytest.mark.parametrize("names", [("RowCopy", "RowCopy"), ("RowCopy", "MAJ3"), ("NOT", "NOT_COPY")])
def test_disjoint_context_progresses_during_another_recovery(names):
    d, r = fixture()
    for i, name in enumerate(names):
        assert d.add(compute(r, name, (i, i), row=10+10*i), i)
        assert d.reserve(i, i)
    events = sorted((clk+2*i, i) for i, name in enumerate(names) for clk in TIMELINES[name])
    overlapped = False
    for clk, i in events:
        d.advance(clk)
        before = {h["engine"]: h for h in d.snapshot()["held"]}
        d.dispatch(i, clk)
        after = {h["engine"]: h for h in d.snapshot()["held"]}
        if before.get(1-i, {}).get("phase") == 3:
            overlapped = True
            assert before[1-i] == after[1-i]
    assert overlapped
    d.advance(max(TOTALS[n]+2*i for i, n in enumerate(names)))
    assert len(d.completions()) == 2
    drained(d)


def test_enqueue_retry_preserves_single_progression_through_promotion():
    d, r = fixture()
    a = compute(r)
    b = compute(r, mats=(16, 17), row=30)
    d.capacity(0, 0)
    assert not d.add(a, 1)
    assert d.snapshot()["held"] == []
    assert d.snapshot()["counters"]["num_pud_rowcopy_reqs"] == 0
    d.capacity(1, 0)
    assert d.add(a.copy(), 1)
    assert d.reserve(1, 0)
    stale = d.save(1)
    d.advance(20)  # Pre-ACT waiting does not relinquish engine or range.
    assert not d.available(b, 1)
    d.dispatch(1, 20)  # First ACT succeeds but promotion cannot enqueue.
    s = d.snapshot()
    assert s["pending"] == 1 and s["active"] == 0 and len(s["held"]) == 1
    assert d.state(1)["cursor"] == 1
    assert not d.add(b.copy(), 2)
    # The retained source is the only schedulable progression; a saved copy
    # is used only to observe invocation expiry, never as a second dispatcher.
    assert d.state(1)["history"] == [20, -1, -1]
    d.capacity(1, 1)
    d.dispatch(1, 60)  # Retry promotion with the authoritative Request progress.
    assert d.snapshot()["active"] == 1 and d.snapshot()["pending"] == 0
    assert d.add(b, 2)
    assert not d.reserve(2, 1)
    assert d.state(2)["cursor"] == 0 and d.state(2)["history"] == [-1, -1, -1]
    d.dispatch(1, 65)
    assert not d.reserve(2, 0) and not d.reserve(2, 1)
    d.advance(80)
    assert not d.reserve(2, 1)
    d.advance(81)
    assert d.saved_expired(stale)
    assert d.reserve(2, 0)
    for clk in TIMELINES["RowCopy"]:
        d.dispatch(2, clk+81)
    d.advance(142)
    assert [e["history"] for e in d.completions()] == [[20, 60, 65], [81, 121, 126]]
    assert d.snapshot()["counters"]["num_pud_rowcopy_reqs"] == 2
    assert d.snapshot()["counters"]["num_pud_rowcopy_reqs_completed"] == 2
    drained(d)


def test_release_and_accounting_precede_reentrant_successor_and_forwarding():
    d, r = fixture()
    a, successor = compute(r), compute(r, "NOT", row=90)

    def callback(event):
        assert event["stats"]["held"] == [] and event["stats"]["delayed"] == 0
        assert event["stats"]["counters"]["num_pud_rowcopy_reqs_completed"] == 1
        assert d.available(successor, 0)
        assert d.add(successor.copy(), 2)
        assert d.reserve(2, 0)
        d.forwarded_read(3)  # Appends to the same deque during its completion scan.

    assert d.add(a, 1, callback)
    assert d.reserve(1, 0)
    for clk in TIMELINES["RowCopy"]:
        d.dispatch(1, clk)
    d.advance(61)
    assert [e["source"] for e in d.completions()] == [1]
    assert d.snapshot()["held"][0]["phase"] == 0
    for clk in TIMELINES["NOT"]:
        d.dispatch(2, clk+61)
    d.advance(160)
    assert [e["source"] for e in d.completions()] == [1, 3, 2]
    assert [e["depart"] for e in d.completions()] == [61, 62, 160]
    assert d.snapshot()["counters"]["num_read_reqs_forwarded"] == 1
    d.advance(170)
    assert len(d.completions()) == 3
    drained(d)


@pytest.mark.parametrize("read_clk", [45, 46, 48, 51])
def test_mixed_read_compute_departure_order_and_same_tick_ready(read_clk):
    d, r = fixture()
    assert d.add(compute(r, "MAJ3"), 1)
    assert d.reserve(1, 0)
    for clk in [0, 11, 16]:
        d.dispatch(1, clk)
    if read_clk < 50:
        d.retire_read(2, read_clk)
    d.dispatch(1, 50)
    if read_clk > 50:
        d.retire_read(2, read_clk)
    d.advance(90)
    # DDR4_2400R read latency is nCL+nBL = 16+4 = 20 CK.
    # Equal departures preserve existing pending insertion order (read first).
    expected = sorted([(read_clk+20, 2), (66, 1)], key=lambda item: item[0])
    assert [(e["depart"], e["source"]) for e in d.completions()] == expected
    assert all(e["depart"] == e["callback_clk"] for e in d.completions())
    drained(d)


@pytest.mark.parametrize("mats,bank,available", [
    ((14, 14), 0, True), ((14, 15), 0, False), ((16, 17), 0, False),
    ((17, 17), 0, True), ((0, 127), 0, False), ((15, 16), 1, True),
])
def test_resource_intersections_use_complete_range_and_bank_identity(mats, bank, available):
    d, r = fixture()
    candidate = compute(r, mats=mats, bank=bank, row=100)
    assert d.add(compute(r, mats=(15, 16)), 1)
    assert d.reserve(1, 0)
    assert d.available(candidate, 1) is available
    for clk in TIMELINES["RowCopy"]:
        d.dispatch(1, clk)
    d.advance(60)
    assert d.available(candidate, 1) is available
    d.advance(61)
    assert d.available(candidate, 0)
    drained(d)


def test_two_recoveries_ready_together_release_exactly_once_with_reentrant_growth():
    d, r = fixture()
    successor = compute(r, mats=(0, 0), row=100)

    def callback(event):
        assert event["stats"]["held"][0]["engine"] == 1
        assert d.add(successor, 3)
        assert d.reserve(3, 0)
        d.forwarded_read(4)

    assert d.add(compute(r, mats=(0, 0)), 1, callback)
    assert d.add(compute(r, mats=(1, 1)), 2)
    assert d.reserve(1, 0) and d.reserve(2, 1)
    d.dispatch(1, 0)
    d.dispatch(2, 1)
    d.dispatch(1, 40)
    d.dispatch(2, 41)
    d.dispatch(1, 46)
    # Synthetic equal-deadline completion fixture, not a two-command bus policy.
    d.dispatch(2, 46, coincident_terminal=True)
    d.advance(61)
    assert d.completions() == [] and len(d.snapshot()["held"]) == 2
    d.advance(62)
    assert [e["source"] for e in d.completions()] == [1, 2]
    assert [e["depart"] for e in d.completions()] == [62, 62]
    assert [h["engine"] for h in d.snapshot()["held"]] == [0]
    assert d.snapshot()["counters"]["num_pud_rowcopy_reqs_completed"] == 2
    for clk in TIMELINES["RowCopy"]:
        d.dispatch(3, clk+62)
    d.advance(130)
    assert [e["source"] for e in d.completions()] == [1, 2, 4, 3]
    assert d.snapshot()["counters"]["num_pud_rowcopy_reqs_completed"] == 3
    drained(d)


@pytest.mark.parametrize("destinations", [2, 5, 32])
def test_multi_destination_recovery_uses_terminal_request_history(destinations):
    d, r = fixture()
    req = request(r, "RowCopy", [descriptor(10+i, (0, 0))
                                for i in range(destinations+1)])
    assert d.add(req, 1) and d.reserve(1, 0)
    times = [0] + [40+5*j for j in range(destinations+1)]
    for clk in times:
        d.dispatch(1, clk)
    depart = times[-1] + 16
    assert d.snapshot()["held"][0]["depart"] == depart
    d.advance(depart-1)
    assert len(d.snapshot()["held"]) == 1 and d.completions() == []
    d.advance(depart)
    event, = d.completions()
    assert event["depart"] == event["callback_clk"] == depart
    assert event["history"] == times
    drained(d)


def test_depart_uses_issue_timestamp_not_later_retirement_clock():
    d, r = fixture()
    assert d.add(compute(r), 1) and d.reserve(1, 0)
    d.dispatch(1, 0)
    d.dispatch(1, 40)
    # Fixture-only delay separates the two clocks; production retires at PRE.
    d.dispatch(1, 45, retirement_delay=5)
    assert d.snapshot()["clk"] == 50
    assert d.snapshot()["held"][0]["depart"] == 61
    d.advance(60)
    assert len(d.snapshot()["held"]) == 1 and d.completions() == []
    d.advance(61)
    event, = d.completions()
    assert event["history"] == [0, 40, 45]
    assert event["depart"] == event["callback_clk"] == 61
    drained(d)
