"""W7 internal admission isolates allocation/arbitration on real GenericDDR."""

import pytest

from ramulator._ramulator_test import _PuDConflictUnderTest
from tests.controller_scheduling.GenericDDRController.test_pud_conflicts import (
    addr, compute, movement, scope,
)
from tests.device_timings.test_pud_compute_ranges import TIMELINES, TOTALS
from tests.unit_tests.test_pud_location import dram_config, resolver
from tests.unit_tests.test_pud_request_locations import controller, synthetic


SCHEDULERS = ["FRFCFS", "FRFCFS-RowHit"]


def fixture(scheduler="FRFCFS", ranks=1, pending=32, refresh=False, **timing):
    config = dram_config(ranks, **timing)
    cfg = controller(config, mapper="PassThroughAddrMapper")
    cfg["scheduler"]["impl"] = scheduler
    cfg["pud_buffer_size"] = pending
    cfg["refresh_manager"]["impl"] = "AllBank" if refresh else "NoRefresh"
    return _PuDConflictUnderTest(cfg), resolver(config=config)


def events(d, source):
    return [e for e in d.issued() if e["source_id"] == source]


def times(d, source):
    return [e["clk"] for e in events(d, source)]


def state(d):
    scheduling = d.scheduling()
    ids = scheduling["unallocated"] + scheduling["allocated"] + scheduling["recovering"]
    return scheduling, d.held(), d.shared(), d.command_occupancy(), [d.compute_state(i) for i in ids]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("name", TOTALS)
def test_real_tick_preserves_local_anchors(scheduler, name):
    d, r = fixture(scheduler)
    assert d.enqueue(compute(r, name), 1)
    d.advance(1 + TOTALS[name])
    assert times(d, 1) == [t+1 for t in TIMELINES[name]]
    assert d.completions()[0]["depart"] == 1 + TOTALS[name]
    assert d.held() == 0


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("count", [9, 12])
def test_disjoint_compute_has_no_engine_capacity_limit(scheduler, count):
    d, r = fixture(scheduler, ranks=4)
    for i in range(count):
        assert d.enqueue(compute(r, "NOT", bank=i % 4, rank=i // 4), i)
    d.advance(1)
    assert d.held() == count
    assert d.compute_state(count-1)["history"] == [-1, -1, -1]
    d.advance(count)
    assert d.scheduling()["allocated"] == list(range(count))
    assert d.scheduling()["unallocated"] == []
    assert [times(d, i) for i in range(count)] == [[i+1] for i in range(count)]
    d.advance(99)  # First terminal PRE has issued; all footprints still recover.
    assert d.held() == count and d.completions() == []
    d.advance(220)
    assert d.held() == 0 and len(d.completions()) == count
    assert len({e["clk"] for e in d.issued()}) == len(d.issued())


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("second", ["RowCopy", "NOT_COPY"])
def test_disjoint_same_subarray_interleaves_and_recovers_independently(scheduler, second):
    d, r = fixture(scheduler)
    assert d.enqueue(compute(r, "RowCopy", (15, 16)), 1)
    assert d.enqueue(compute(r, second, (17, 20)), 2)
    d.advance(46)
    assert d.scheduling()["recovering"] == [1]
    assert d.scheduling()["allocated"] == [2]
    assert d.held() == 2
    assert times(d, 1) == [1, 41, 46]
    assert times(d, 2)[:2] == [2, 42]
    d.advance(150)
    assert times(d, 2) == [t+2 for t in TIMELINES[second]]
    assert [e["depart"] for e in d.completions()] == [62, 2+TOTALS[second]]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("mats,row", [((16, 17), 40), ((100, 101), 1034)])
def test_intersecting_ranges_and_other_subarrays_wait_through_recovery(scheduler, mats, row):
    d, r = fixture(scheduler)
    assert d.enqueue(compute(r, mats=(15, 16)), 1)
    assert d.enqueue(compute(r, mats=mats, row=row), 2)
    d.advance(61)
    assert d.scheduling()["unallocated"] == [2]
    assert d.compute_state(2)["phase"] == -1 and times(d, 2) == []
    d.advance(62)
    assert times(d, 2) == [62]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_first_fit_skips_blocked_oldest_then_restores_its_age_priority(scheduler):
    d, r = fixture(scheduler)
    assert d.enqueue(compute(r), 1)  # A
    d.advance(1)
    assert d.enqueue(compute(r, row=40), 2)  # B conflicts despite different rows.
    d.advance(2)
    assert d.scheduling()["unallocated"] == [2] and d.held() == 1
    assert d.enqueue(compute(r, "NOT", (2, 2)), 3)  # C fits.
    assert d.enqueue(compute(r, mats=(3, 3)), 4)  # D also fits and acquires protection.
    d.advance(3)
    assert d.scheduling()["allocated"] == [1, 3, 4]
    assert d.scheduling()["unallocated"] == [2]
    assert times(d, 3) == [3] and times(d, 2) == times(d, 4) == []
    d.advance(61)
    assert d.compute_state(2)["phase"] == -1
    assert times(d, 4) == [4, 44, 49]
    d.advance(62)
    assert d.scheduling()["allocated"] == [2, 3]
    assert d.scheduling()["recovering"] == [4]
    assert d.scheduling()["unallocated"] == []
    assert times(d, 2) == [62]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_allocation_precedes_blocked_first_act_and_probes_own_nothing(scheduler):
    d, r = fixture(scheduler)
    req = compute(r)
    assert d.enqueue(req, 1)
    assert d.enqueue(compute(r, mats=(2, 2)), 2)
    assert d.enqueue(compute(r, mats=(3, 3)), 3)
    before = state(d)
    for _ in range(3):
        assert not d.scheduled_probe(1)
        assert d.allocation_probe(req)
        assert state(d) == before
    d.block_command_bus(10)  # Ordinary/shared issue occupancy, no target transport.
    d.advance(1)
    assert d.scheduling()["allocated"] == [1, 2, 3]
    assert d.scheduling()["unallocated"] == []
    assert d.held() == 3 and d.issued() == []
    assert d.compute_state(1)["phase"] == 0
    before = state(d)
    for _ in range(3):
        assert not d.scheduled_probe(1)
        assert not d.allocation_probe(req)
        assert state(d) == before
    d.advance(10)
    assert times(d, 1) == [10]
    d.advance(11)
    assert times(d, 2) == [11]  # Older allocated 1 is locally blocked.


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("name", ["LC-MOV", "GB-MOV"])
@pytest.mark.parametrize("active_capacity", [0, 32])
def test_other_bank_movement_and_ordinary_work_use_compute_gaps(scheduler, name, active_capacity):
    d, r = fixture(scheduler)
    d.capacity(active_capacity)
    assert d.enqueue(compute(r, "NOT"), 1)
    assert d.enqueue(compute(r, "NOT", bank=3), 4)
    d.movement(movement(r, name, bank=1), 2)
    d.send(0, addr(bank=2), 3)
    d.advance(39)
    assert d.held() == 2 and times(d, 4) == [2]
    assert events(d, 2)[0]["command"] == "ACT_MOV"
    assert any(e["command"] == "RD" for e in events(d, 3))
    assert times(d, 2)[0] < 40 and times(d, 3)[0] < 40
    d.advance(250)
    assert len(d.completions()) == 3  # Two compute and one movement callbacks.
    assert len({e["clk"] for e in d.issued()}) == len(d.issued())


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_maintenance_arrival_stops_admission_and_drains_allocated_work(scheduler):
    d, r = fixture(scheduler, nRFC=20)
    assert d.enqueue(compute(r), 1)
    assert d.enqueue(compute(r, "NOT", (2, 2)), 2)
    d.advance(2)
    d.priority("REFab", scope())
    assert d.enqueue(compute(r, mats=(3, 3)), 3)
    d.advance(100)
    assert d.scheduling()["unallocated"] == [3]
    assert not any(e["command"] == "REFab" for e in d.issued())
    d.advance(101)
    assert d.held() == 0
    assert d.issued()[-1]["command"] == "REFab"
    d.advance(120)
    assert times(d, 3) == []
    d.advance(121)
    assert times(d, 3) == [121]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_pending_capacity_backpressure_and_reentrant_release_reuse(scheduler):
    d, r = fixture(scheduler, pending=2)
    d.capacity(0)
    callbacks = []

    def reuse(event):
        callbacks.append(event)
        assert event["held"] == 1
        assert event["stats"]["num_pud_rowcopy_reqs_completed"] == 1
        assert d.enqueue(compute(r), 3)

    assert d.enqueue(compute(r), 1, reuse)
    assert d.enqueue(compute(r, "NOT", (2, 2)), 2)
    before = state(d)
    assert not d.enqueue(compute(r, mats=(3, 3)), 4)
    assert state(d) == before
    d.advance(2)
    assert d.held() == 2 and d.scheduling()["active_size"] == 0
    assert d.scheduling()["pud_size"] == 2
    d.advance(62)
    assert len(callbacks) == 1 and times(d, 3) == [62]
    assert d.compute_state(3)["phase"] == 2
    d.advance(200)
    assert [e["source"] for e in d.completions()] == [1, 2, 3]
    assert d.held() == 0 and d.stats()["num_pud_rowcopy_reqs_completed"] == 2


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_conventional_activity_prepares_then_recovers_before_allocation(scheduler):
    d, r = fixture(scheduler)
    d.send(0, addr(row=100), 2)
    d.advance(1)
    assert d.enqueue(compute(r), 1)
    d.advance(39)
    assert d.held() == 0 and times(d, 1) == []
    d.advance(40)
    assert events(d, 1)[0]["command"] == "PREpb"
    assert d.compute_state(1)["cursor"] == 0 and d.held() == 0
    d.advance(55)
    assert d.held() == 0
    d.advance(56)
    assert d.held() == 1 and events(d, 1)[1]["command"] == "ACT_PUD_S_OC"


@pytest.mark.parametrize("value", [None, 0, -1, 1, 8, 1024])
def test_removed_engine_parameter_is_rejected_in_raw_config(value):
    cfg = controller(dram_config(), mapper="PassThroughAddrMapper")
    cfg["pud_compute_engines"] = value
    with pytest.raises(RuntimeError, match="pud_compute_engines has been removed"):
        _PuDConflictUnderTest(cfg)


def test_replacement_profile_owns_range_segmentation():
    r, config = synthetic()
    cfg = controller(config, mapper="PassThroughAddrMapper")
    d = _PuDConflictUnderTest(cfg)
    for source, mats in [(1, (7, 8)), (2, (8, 9)), (3, (10, 11))]:
        assert d.enqueue(compute(r, mats=mats, row=10*source), source)
    d.advance(2)
    assert d.scheduling()["allocated"] == [1, 3]
    assert d.scheduling()["unallocated"] == [2]
    assert d.compute_state(1)["occurrences"][0]["segments"] == [[0, 7, 7], [1, 0, 0]]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_generated_refresh_precedes_admission_and_drains_existing_allocation(scheduler):
    d, r = fixture(scheduler, refresh=True, nREFI=64, nRFC=2)
    assert d.enqueue(compute(r, "NOT"), 1)
    d.advance(63)
    assert d.enqueue(compute(r, mats=(2, 2)), 2)
    d.advance(64)  # Refresh generated before allocation in this very tick.
    assert d.scheduling()["unallocated"] == [2]
    d.advance(99)
    assert not any(e["command"] == "REFab" for e in d.issued())
    d.advance(100)
    assert d.issued()[-1]["command"] == "REFab" and d.held() == 0
    d.advance(101)
    assert times(d, 2) == []
    d.advance(102)
    assert times(d, 2) == [102]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_priority_fifo_blocks_other_rank_admission_but_allocated_context_drains(scheduler):
    d, r = fixture(scheduler, ranks=4, nRFC=20)
    assert d.enqueue(compute(r, "NOT"), 1)
    d.advance(1)
    d.priority("REFab", scope(0))
    d.priority("REFab", scope(1))
    assert d.enqueue(compute(r, rank=2), 2)
    d.send(0, addr(rank=3), 3)
    d.advance(99)
    assert d.scheduling()["unallocated"] == [2]
    assert times(d, 3) == []
    assert all(e["source_id"] == 1 for e in d.issued())
    d.advance(101)
    assert [(e["clk"], e["addr_vec"][1]) for e in d.issued() if e["command"] == "REFab"] == [(100, 0), (101, 1)]
    d.advance(102)
    assert times(d, 2) == [102]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_whole_range_rejection_cannot_partially_own_a_free_segment(scheduler):
    d, r = fixture(scheduler)
    assert d.enqueue(compute(r, "NOT", (16, 16)), 1)
    d.advance(1)
    blocked = compute(r, mats=(14, 17), row=40)
    before = state(d)
    for _ in range(3):
        assert not d.allocation_probe(blocked)
        assert state(d) == before
    assert d.enqueue(blocked, 2)
    assert d.enqueue(compute(r, mats=(14, 15)), 3)
    d.advance(2)
    assert d.scheduling()["unallocated"] == [2]
    assert d.scheduling()["allocated"] == [1, 3]
    assert d.compute_state(2)["phase"] == -1


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_ready_priority_in_another_rank_uses_a_compute_local_gap(scheduler):
    d, r = fixture(scheduler, ranks=4)
    assert d.enqueue(compute(r, "NOT"), 1)
    d.advance(1)
    d.priority("REFab", scope(1))
    d.advance(2)
    assert d.issued()[-1]["command"] == "REFab"
    assert d.held() == 1 and times(d, 1) == [1]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("change", ["command", "timing"])
def test_compute_final_issue_rechecks_after_selection_without_advancing(scheduler, change):
    d, r = fixture(scheduler)
    assert d.enqueue(compute(r), 1)
    before = d.shared()
    if change == "command":
        d.recheck_tick("PREab")
    else:
        d.recheck_tick(callback=lambda: d.block_command_bus(2))
    assert d.shared() == before and d.issued() == []
    assert d.held() == 1 and d.compute_state(1)["phase"] == 0
    assert d.compute_state(1)["cursor"] == 0 and d.compute_state(1)["history"] == [-1, -1, -1]
    d.advance(2)
    assert times(d, 1) == [2]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_late_protection_rejects_selected_ordinary_command(scheduler):
    d, r = fixture(scheduler)
    d.send(0, addr(), 2)
    before = d.shared()

    def reserve_after_selection():
        assert d.add(compute(r), 1)

    d.recheck_tick(callback=reserve_after_selection)
    assert d.shared() == before and d.issued() == [] and d.held() == 1


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_oldest_active_ordinary_request_preserves_precedence(scheduler):
    d, r = fixture(scheduler)
    d.send(0, addr(bank=1), 2)
    d.advance(16)
    assert d.enqueue(compute(r), 1)
    d.advance(17)  # Ordinary RD and first compute ACT are both ready.
    assert events(d, 2)[-1]["command"] == "RD" and times(d, 1) == []
    assert d.held() == 1
    d.advance(18)
    assert times(d, 1) == [18]


def test_physical_protection_is_independent_between_controller_instances():
    first, r = fixture()
    second, s = fixture()
    assert first.enqueue(compute(r), 1)
    assert second.enqueue(compute(s), 1)
    first.advance(1)
    second.advance(1)
    assert first.held() == second.held() == 1
    assert first.compute_state(1)["phase"] == second.compute_state(1)["phase"] == 2


def test_internal_enqueue_seam_does_not_accept_movement():
    d, r = fixture()
    before = state(d)
    with pytest.raises(RuntimeError, match="requires located compute"):
        d.enqueue(movement(r, "LC-MOV"), 1)
    assert state(d) == before


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("other_subarray", [False, True])
def test_more_than_eight_protected_footprints_keep_conflicts_until_recovery(scheduler, other_subarray):
    d, r = fixture(scheduler)
    for i in range(9):
        assert d.enqueue(compute(r, "NOT", mats=(i, i)), i)
    # Same mat conflicts despite different rows. Different subarrays in the
    # same Bank conflict even with disjoint mats (the unchanged no-SALP policy).
    assert d.enqueue(compute(r, mats=(20, 20) if other_subarray else (0, 0),
                             row=1034 if other_subarray else 100), 9)
    d.advance(9)
    assert d.held() == 9 and d.scheduling()["unallocated"] == [9]
    release = 108 if other_subarray else 100
    d.advance(release-1)
    assert times(d, 9) == []
    assert d.scheduling()["recovering"]  # Terminal commands no longer scheduled.
    d.advance(release)
    assert times(d, 9) == [release]
    d.advance(200)
    assert len(d.completions()) == 10 and d.held() == 0


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("command", ["PREpb", "PREab", "REFab", "RD", "WR"])
def test_conventional_work_waits_for_all_nine_active_and_recovering_footprints(scheduler, command):
    d, r = fixture(scheduler)
    for i in range(9):
        assert d.enqueue(compute(r, "NOT", mats=(i, i)), i)
    d.advance(1)
    if command in ("RD", "WR"):
        d.send(0 if command == "RD" else 1, addr(), 9)
    else:
        d.priority(command, addr() if command == "PREpb" else scope())
    for clk in (9, 84, 99, 107):
        d.advance(clk)
        assert not d.probe(command, command, addr() if command not in ("PREab", "REFab") else scope())["eligible"]
        assert all(e["source_id"] in range(9) for e in d.issued())
    d.advance(108)
    assert d.held() == 0
    assert d.issued()[-1]["command"] == ("ACT" if command in ("RD", "WR") else command)
    d.advance(300)
    assert len(d.completions()) == 9


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("initial", ["PREpb", "ACT"])
def test_nine_disjoint_invocations_do_not_bypass_conventional_bank_state_or_timing(scheduler, initial):
    d, r = fixture(scheduler)
    d.raw(initial, addr(bank=1), True)
    for i in range(9):
        assert d.enqueue(compute(r, "NOT", mats=(i, i)), i)
    assert d.enqueue(compute(r, bank=1), 9)
    d.advance(9)
    assert d.held() == 9 and d.scheduling()["unallocated"] == [9]
    admission = 16 if initial == "PREpb" else 55
    d.advance(admission-1)
    assert d.compute_state(9)["phase"] == -1
    if initial == "ACT":
        assert [(e["command"], e["clk"]) for e in events(d, 9)] == [("PREpb", 39)]
    else:
        assert times(d, 9) == []
    d.advance(admission)
    assert events(d, 9)[-1]["command"] == "ACT_PUD_S_OC"
    assert events(d, 9)[-1]["clk"] == admission
    d.advance(220)
    assert len(d.completions()) == 10


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("name", ["LC-MOV", "GB-MOV"])
def test_movement_progresses_with_nine_compute_invocations_and_keeps_dependencies(scheduler, name):
    d, r = fixture(scheduler)
    for i in range(9):
        assert d.enqueue(compute(r, "NOT", mats=(i, i)), i)
    d.movement(movement(r, name, mat=20), 9)
    # This movement intersects the first movement; its first ACT must wait
    # for the producer footprint's terminal recovery.
    d.movement(movement(r, name, mat=20), 10)
    d.advance(20)
    assert d.held() == 9 and events(d, 9)[0]["command"] == "ACT_MOV"
    assert times(d, 10) == []
    d.advance(400)
    done = {e["source"]: e["depart"] for e in d.completions()}
    assert len(done) == 11 and d.held() == 0
    assert times(d, 9)[0] < min(done[i] for i in range(9))
    assert times(d, 10)[0] >= done[9]  # Ready work still competes for command issue.
    for source in (9, 10):
        t = times(d, source)
        assert done[source] == t[-1] + 16
        if name == "LC-MOV":
            assert t[2]-t[0] >= 39
            assert all(b-a >= delay for a, b, delay in zip(t, t[1:], (16, 23, 16, 39, 20)))
        else:
            assert t[2]-t[0] >= 39 and t[3]-t[2] >= 2 and t[4]-t[3] >= 18
    assert len({e["clk"] for e in d.issued()}) == len(d.issued())
