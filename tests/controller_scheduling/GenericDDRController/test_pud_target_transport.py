"""W6 transport on real GenericDDR with explicitly pre-reserved W4 contexts."""

import pytest

from tests.controller_scheduling.GenericDDRController.test_pud_conflicts import (
    addr, compute, fixture, movement, scope,
)
from tests.device_timings.test_pud_compute_ranges import COMMANDS, TIMELINES, TOTALS
from tests.unit_tests.test_pud_request_locations import COMPUTE, controller, descriptor, request, synthetic
from ramulator._ramulator_test import _PuDConflictUnderTest


def entries(d, clk, chip=0, rank=0):
    return next((q["entries"] for q in d.targets(clk)["queues"]
                 if q["chip"] == [0, rank, chip]), [])


def snapshot(d, clk, *ids):
    return d.targets(clk), d.shared(), [d.transport_state(i) for i in ids], d.held()


def setup(d, source, clk, **kwargs):
    d.advance(clk)
    before = snapshot(d, clk, source)
    for _ in range(3):
        assert d.target_setup(source, **kwargs)
        assert snapshot(d, clk, source) == before
    assert d.target_setup(source, issue=True, **kwargs)


def issue(d, source, clk):
    d.advance(clk)
    before = snapshot(d, clk, source)
    for _ in range(3):
        assert d.transport_dispatch(source)
        assert snapshot(d, clk, source) == before
    assert d.transport_dispatch(source, issue=True)


def blocked(d, source, clk, preparation=False, **kwargs):
    d.advance(clk)
    before = snapshot(d, clk, source)
    method = d.target_setup if preparation else d.transport_dispatch
    for _ in range(3):
        assert not method(source, **kwargs)
        assert snapshot(d, clk, source) == before
    with pytest.raises(RuntimeError, match="not ready"):
        method(source, issue=True, **kwargs)
    assert snapshot(d, clk, source) == before


@pytest.mark.parametrize("name", COMPUTE)
@pytest.mark.parametrize("mats", [(0, 0), (15, 16), (0, 127)])
def test_exact_transport_counts_boundaries_and_local_anchors(name, mats):
    d, r = fixture()
    assert d.add(compute(r, name, mats), 1, 0)
    blocked(d, 1, 0)  # Allocation does not prepare even the first ACT.
    shared = d.shared()
    setup(d, 1, 0)
    assert d.shared() == shared and d.transport_state(1)["cursor"] == 0
    blocked(d, 1, 0)
    transports = 0
    for index, (relative, command) in enumerate(zip(TIMELINES[name], COMMANDS[name])):
        clk = relative + 1
        if index:
            blocked(d, 1, clk-1)
        old_queue = d.targets(clk)["queues"]
        issue(d, 1, clk)
        if command.startswith("ACT"):
            later = [i for i in range(index+1, len(COMMANDS[name])) if COMMANDS[name][i].startswith("ACT")]
            if later:
                transports += 1
                for q in d.targets(clk)["queues"]:
                    e, = q["entries"]
                    assert (e["index"], e["transmit"], e["ready_at"]) == (later[0], clk+1, clk+2)
                    assert e["reserved"] and not e["ready"]
                d.advance(clk+1)
                for q in d.targets(clk+1)["queues"]:
                    assert not q["entries"][0]["reserved"] and not q["entries"][0]["ready"]
                d.advance(clk+2)
                assert all(q["entries"][0]["ready"] for q in d.targets(clk+2)["queues"])
            else:
                assert not any(q["entries"] for q in d.targets(clk)["queues"])
        elif command == "N":
            assert d.targets(clk)["queues"] == old_queue
    assert transports == dict(RowCopy=1, MAJ3=2, MAJ5=4, NOT=0, NOT_COPY=1)[name]
    assert d.transport_state(1)["history"] == [t+1 for t in TIMELINES[name]]
    d.advance(TOTALS[name])
    assert d.held() == 1 and d.completions() == []
    d.advance(TOTALS[name]+1)
    assert d.held() == 0 and d.completions()[0]["depart"]-1 == TOTALS[name]


@pytest.mark.parametrize("destinations", [2, 5, 32])
@pytest.mark.parametrize("mats", [(0, 0), (15, 16), (0, 127)])
def test_rowcopy_successors_even_for_identical_numeric_ranges(destinations, mats):
    d, r = fixture()
    req = request(r, "RowCopy", [descriptor(10+i, mats) for i in range(destinations+1)])
    assert d.add(req, 1, 0)
    setup(d, 1, 0)
    clocks = [1] + [41+5*i for i in range(destinations+1)]
    sent = 0
    for clk in clocks:
        issue(d, 1, clk)
        q = next(iter(d.targets(clk)["queues"]))["entries"]
        if q:
            assert q[0]["transmit"] == clk+1
            sent += 1
    assert sent == destinations
    d.advance(1+40+5*destinations+16)
    assert d.held() == 0


def test_exact_eight_ninth_blocked_space_released_while_engines_busy():
    d, r = fixture()
    for i in range(9):
        assert d.add(compute(r, "NOT", (i, i)), i, i)
    for i in range(8):
        setup(d, i, i)
    assert len(entries(d, 8)) == 8 and d.held() == 9
    blocked(d, 8, 8, preparation=True)
    issue(d, 0, 8)
    assert len(entries(d, 8)) == 7 and d.held() == 9
    setup(d, 8, 9)
    assert len(entries(d, 9)) == 8 and d.held() == 9


def test_multi_chip_partial_capacity_and_mismatched_heads_are_atomic():
    d, r = fixture()
    for i in range(8):
        assert d.add(compute(r, "NOT", (16+i, 16+i)), i, i)
        setup(d, i, i)
    assert d.add(compute(r, "NOT", (15, 16), bank=1), 8, 8)
    blocked(d, 8, 8, preparation=True)
    assert entries(d, 8, chip=0) == []
    blocked(d, 8, 8)  # No descriptors on either chip.
    issue(d, 0, 8)
    setup(d, 8, 9)
    blocked(d, 8, 10)  # Matching chip-0 head cannot consume while chip-1 mismatches.
    assert entries(d, 10, chip=0)[0]["source"] == 8
    for i in range(1, 8):
        issue(d, i, 9+i)
    issue(d, 8, 17)
    assert entries(d, 17, chip=0) == entries(d, 17, chip=1) == []


def test_successor_credit_cannot_be_stolen_at_full_capacity():
    d, r = fixture()
    for i in range(9):
        assert d.add(compute(r, "RowCopy" if i == 0 else "NOT", (i, i)), i, i)
    for i in range(8):
        setup(d, i, i)
    issue(d, 0, 8)
    q = entries(d, 8)
    assert len(q) == 8 and q[-1]["source"] == 0 and q[-1]["reserved"]
    blocked(d, 8, 9, preparation=True)  # Mandatory C/A cycle.
    blocked(d, 8, 10, preparation=True)  # Its reserved credit remains occupied.
    for i in range(1, 8):
        issue(d, i, 9+i)
    setup(d, 8, 17)
    blocked(d, 0, 47)
    issue(d, 0, 48)
    assert [e["source"] for e in entries(d, 48)] == [8]


def test_queues_shared_across_banks_isolated_across_chips_and_ranks():
    d, r = fixture(ranks=4)
    for i, (bank, rank, mats) in enumerate([(0, 0, (0, 0)), (1, 0, (0, 0)),
                                           (0, 1, (0, 0)), (0, 0, (16, 16))]):
        assert d.add(compute(r, "NOT", mats, bank=bank, rank=rank), i, i)
        setup(d, i, i)
    assert [e["source"] for e in entries(d, 4)] == [0, 1]
    blocked(d, 1, 4)
    issue(d, 2, 4)
    issue(d, 3, 5)
    issue(d, 0, 6)
    issue(d, 1, 7)


@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
def test_staggered_multi_chip_fifo_progress_and_maintenance_drain(scheduler):
    d, r = fixture(scheduler)
    for i, mats in enumerate([(14, 15), (15, 16), (16, 17)]):
        assert d.add(compute(r, mats=mats, bank=i), i, i)
        setup(d, i, i)
    for i in range(3):
        issue(d, i, 3+2*i)
    d.priority("REFab", scope())
    assert not d.start(compute(r, bank=3))
    for clk, i in [(43, 0), (45, 1), (47, 2), (48, 0), (50, 1), (52, 2)]:
        issue(d, i, clk)
    d.advance(67)
    assert not d.issued() and d.held() == 1
    d.advance(68)
    assert d.held() == 0 and [e["command"] for e in d.issued()] == ["REFab"]


@pytest.mark.parametrize("late", [0, 37])
def test_cold_or_late_setup_does_not_reuse_historical_pre(late):
    d, r = fixture()
    d.raw("PREpb", addr(), True)  # Earlier PRE knows nothing about the future request.
    d.advance(16+late)
    assert d.add(compute(r, "NOT"), 1, 0)
    blocked(d, 1, 16+late)
    setup(d, 1, 16+late)
    assert entries(d, 16+late)[0]["transmit"] == 16+late
    issue(d, 1, 17+late)


def test_useful_conventional_pre_pairs_distinct_bank_target_and_close():
    d, r = fixture()
    d.raw("ACT", addr(bank=1), True)
    assert d.add(compute(r, "NOT"), 1, 0)
    blocked(d, 1, 38, preparation=True, pre_command="PREpb", addr=addr(bank=1))
    before = d.transport_state(1)
    setup(d, 1, 39, pre_command="PREpb", addr=addr(bank=1))
    assert d.transport_state(1) == before
    e, = entries(d, 39)
    assert e["external"][3] == 0 and e["ready_at"] == 40
    assert not d.probe("ACT", "ACT", addr(bank=1))["issue"]
    issue(d, 1, 40)
    d.advance(55)
    assert d.probe("ACT", "ACT", addr(bank=1))["issue"]


def test_range_pre_prepares_disjoint_context_without_reset_or_recovery_shift():
    d, r = fixture()
    assert d.add(compute(r, "NOT", (0, 0)), 1, 0)
    assert d.add(compute(r, "MAJ3", (1, 1)), 2, 1)
    setup(d, 1, 0)
    issue(d, 1, 1)
    issue(d, 1, 41)
    blocked(d, 2, 83, preparation=True, close_source=1)
    setup(d, 2, 84, close_source=1)
    assert d.transport_state(1)["phase"] == 3 and d.transport_state(2)["phase"] == 0
    assert d.transport_state(1)["history"] == [1, 41, 84]
    issue(d, 2, 85)  # Does not inherit the other range's PRE + nRP.
    assert d.transport_state(1)["phase"] == 3
    d.advance(100)
    assert d.completions()[0]["depart"] == 100


@pytest.mark.parametrize("pre", ["PREpb", "PREab"])
def test_no_unnecessary_bank_close_or_protected_scope_pre(pre):
    d, r = fixture()
    assert d.add(compute(r, "NOT"), 1, 0)
    target = addr(bank=1) if pre == "PREpb" else scope(rank=1)
    if pre == "PREab":
        d, r = fixture(ranks=4)
        assert d.add(compute(r, "NOT"), 1, 0)
    blocked(d, 1, 0, preparation=True, pre_command=pre, addr=target)  # Empty close scope.
    blocked(d, 1, 0, preparation=True, pre_command=pre,
            addr=addr() if pre == "PREpb" else scope())  # Protected scope.
    setup(d, 1, 0)


def test_maintenance_arrival_rejects_pre_pair_before_mutation_but_allocation_drains():
    d, r = fixture()
    d.raw("ACT", addr(bank=1), True)
    assert d.add(compute(r, "NOT"), 1, 0)
    d.advance(39)
    assert d.target_setup(1, pre_command="PREpb", addr=addr(bank=1))
    d.priority("REFab", scope())
    blocked(d, 1, 39, preparation=True, pre_command="PREpb", addr=addr(bank=1))
    # The waiting maintenance cannot strand its already allocated blocker.
    setup(d, 1, 39)
    for clk in [40, 80, 123]:
        issue(d, 1, clk)
    d.advance(139)
    assert d.held() == 0 and [e["command"] for e in d.issued()] == ["PREab"]
    d.advance(155)
    assert [e["command"] for e in d.issued()] == ["PREab", "REFab"]


def test_no_unallocated_request_can_prepare_targets():
    d, r = fixture()
    before = snapshot(d, 0)
    for mutate in [False, True]:
        with pytest.raises(RuntimeError, match="protected compute context"):
            d.unallocated_setup(compute(r), mutate)
        assert snapshot(d, 0) == before


@pytest.mark.parametrize("command", ["ACT", "ACT_MOV"])
def test_mandatory_successor_slot_excludes_other_bank_command_and_failed_issue(command):
    d, r = fixture()
    assert d.add(compute(r), 1, 0)
    setup(d, 1, 0)
    issue(d, 1, 1)
    d.advance(2)
    before = snapshot(d, 2, 1)
    assert not d.probe(command, command, addr(bank=1))["issue"]
    with pytest.raises(RuntimeError, match="C/A reserved"):
        d.raw(command, addr(bank=1), True)
    assert snapshot(d, 2, 1) == before
    d.advance(3)
    assert d.probe(command, command, addr(bank=1))["issue"]


@pytest.mark.parametrize("name", ["LC-MOV", "GB-MOV"])
@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
def test_scheduled_movement_competes_for_ca_without_compute_queue_tokens(name, scheduler):
    d, r = fixture(scheduler)
    assert d.add(compute(r), 1, 0)
    setup(d, 1, 0)
    issue(d, 1, 1)
    d.movement(movement(r, name, bank=1), 2)
    d.advance(2)
    assert not d.issued()
    d.advance(3)
    assert [(e["command"], e["clk"]) for e in d.issued()] == [("ACT_MOV", 3)]
    assert {e["source"] for q in d.targets(3)["queues"] for e in q["entries"]} == {1}
    for clk in [41, 46]:
        issue(d, 1, clk)
    total = 130 if name == "LC-MOV" else 75
    d.advance(3+total)
    event = next(e for e in d.completions() if e["source"] == 2)
    assert event["depart"] == 3+total


def test_nonidentity_profile_supplies_chip_and_local_range():
    r, config = synthetic()
    d = _PuDConflictUnderTest(controller(config, mapper="PassThroughAddrMapper"))
    assert d.add(compute(r, "NOT_COPY", (7, 8)), 1, 0)
    setup(d, 1, 0)
    assert [q["entries"][0]["segment"] for q in d.targets(0)["queues"]] == [[0, 7, 7], [1, 0, 0]]
    for clk in [1, 41, 84, 89]:
        issue(d, 1, clk)
    d.advance(105)
    assert d.held() == 0


def test_full_multi_chip_queue_prevents_pre_close_and_reserves_successor_credit():
    d, r = fixture()
    d.raw("ACT", addr(bank=3, bg=3), True)
    for i in range(9):
        assert d.add(compute(r, "RowCopy" if i == 0 else "NOT", (15, 16),
                             bank=i % 4, bg=i // 4), i, i)
    for i in range(8):
        setup(d, i, 1+i)
    blocked(d, 8, 39, preparation=True, pre_command="PREpb", addr=addr(bank=3, bg=3))
    issue(d, 0, 39)
    for chip in (0, 1):
        q = entries(d, 39, chip=chip)
        assert len(q) == 8 and q[-1]["source"] == 0 and q[-1]["reserved"]
    blocked(d, 8, 40, preparation=True)
    blocked(d, 8, 41, preparation=True)
    issue(d, 1, 41)
    setup(d, 8, 42, pre_command="PREpb", addr=addr(bank=3, bg=3))
    assert all(len(entries(d, 42, chip=chip)) == 8 for chip in (0, 1))


def test_repeated_setup_and_same_cycle_ordinary_issue_cannot_mutate_queue():
    d, r = fixture()
    assert d.add(compute(r), 1, 0)
    d.raw("ACT", addr(bank=1), True)
    blocked(d, 1, 0, preparation=True)
    setup(d, 1, 1)
    blocked(d, 1, 2, preparation=True)  # Exact invocation/occurrence already queued.
    issue(d, 1, 2)


def test_range_pre_pair_during_maintenance_drain():
    d, r = fixture()
    for i in (0, 1):
        assert d.add(compute(r, "NOT", (i, i)), i, i)
    setup(d, 0, 0)
    issue(d, 0, 1)
    issue(d, 0, 41)
    d.priority("REFab", scope())
    setup(d, 1, 84, close_source=0)
    for clk in (85, 125, 168):
        issue(d, 1, clk)
    d.advance(184)
    assert d.held() == 0 and [e["command"] for e in d.issued()] == ["REFab"]


@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
def test_scheduled_ordinary_command_waits_for_successor_ca_cycle(scheduler):
    d, r = fixture(scheduler)
    assert d.add(compute(r), 1, 0)
    setup(d, 1, 0)
    issue(d, 1, 1)
    d.send(0, addr(bank=1), 2)
    d.advance(2)
    assert not d.issued()
    d.advance(3)
    assert [(e["command"], e["clk"]) for e in d.issued()] == [("ACT", 3)]


def test_useful_rank_pre_preserves_distinct_rank_recovery():
    d, r = fixture(ranks=4)
    d.raw("ACT", addr(rank=1), True)
    assert d.add(compute(r, "NOT"), 1, 0)
    setup(d, 1, 39, pre_command="PREab", addr=scope(rank=1))
    issue(d, 1, 40)
    d.advance(54)
    assert not d.probe("ACT", "ACT", addr(rank=1))["issue"]
    d.advance(55)
    assert d.probe("ACT", "ACT", addr(rank=1))["issue"]
