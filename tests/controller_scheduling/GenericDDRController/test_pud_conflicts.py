"""W5 exclusion on real GenericDDR; compute dispatch is an internal fixture."""
import itertools

import pytest

from ramulator._ramulator_test import _PuDConflictUnderTest, _located_lifetime
from tests.device_timings.test_pud_compute_ranges import TIMELINES, TOTALS
from tests.unit_tests.test_pud_location import dram_config, resolver
from tests.unit_tests.test_pud_request_locations import COMPUTE, controller, descriptor, request

MOVES = {"LC-MOV": ([0, 16, 39, 55, 94, 114], 130),
         "GB-MOV": ([0, 1, 39, 41, 59], 75)}


def fixture(scheduler="FRFCFS", ranks=1, policy="Open", refresh=False, **timing):
    config = dram_config(ranks, **timing)
    cfg = controller(config, mapper="PassThroughAddrMapper")
    cfg["scheduler"]["impl"] = scheduler
    cfg["refresh_manager"]["impl"] = "AllBank" if refresh else "NoRefresh"
    cfg["row_policy"] = dict(impl=policy, **({"cap": 1} if policy == "ClosedCAP" else {}))
    return _PuDConflictUnderTest(cfg), resolver(config=config)


def addr(bank=0, rank=0, bg=0, row=100):
    return [0, rank, bg, bank, row, 0]


def scope(rank=0):
    return [0, rank, -1, -1, -1, -1]


def compute(r, name="RowCopy", mats=(0, 0), bank=0, rank=0, bg=0, row=10):
    desc = [descriptor(row+i, mats) for i in range(COMPUTE[name])]
    for item in desc:
        item["row"] = [0, rank, bg, bank, item["row"][4]]
    return request(r, name, desc)


def movement(r, name, bank=0, mat=8):
    desc = [descriptor(20+i, (mat+i, mat+i) if name == "GB-MOV" else (mat, mat), 3+i)
            for i in range(2)]
    for item in desc:
        item["row"][3] = bank
    return request(r, name, desc)


def finish(d, source, name="RowCopy", offset=0):
    for clk in TIMELINES[name]:
        d.dispatch(source, clk+offset)


@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
@pytest.mark.parametrize("phase", ["allocated", "sharing", "N", "recovery"])
@pytest.mark.parametrize("command", ["ACT", "RD", "WR", "RDA", "WRA", "PREpb",
                                    "ACT_MOV", "PREab", "REFab"])
def test_protected_scope_blocks_before_prerequisite_and_final_issue(scheduler, phase, command):
    d, r = fixture(scheduler)
    name = "NOT" if phase == "N" else "MAJ3"
    assert d.add(compute(r, name, bank=3, bg=3), 1)
    if phase == "sharing":
        d.dispatch(1, 0)
    elif phase == "N":
        d.dispatch(1, 0)
        d.dispatch(1, 40)
    elif phase == "recovery":
        finish(d, 1, name)
        d.advance(TOTALS[name]-1)
    target = scope() if command in ("PREab", "REFab") else addr(3, bg=3)
    before = d.shared()
    result = d.probe(command, command, target)
    assert result["eligible"] is False and result["preq"] is None and result["issue"] is False
    if command in ("PREpb", "PREab", "RDA", "WRA"):
        assert result["close"]
    for issue in (False, True):
        with pytest.raises(RuntimeError, match="protected PuD invocation"):
            d.raw(command, target, issue)
        assert d.shared() == before


@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
@pytest.mark.parametrize("name", MOVES)
def test_compute_blocks_real_movement_through_recovery(scheduler, name):
    d, r = fixture(scheduler)
    assert d.add(compute(r), 1)
    d.movement(movement(r, name, mat=0), 2)  # Intersecting physical mats conflict.
    d.advance(5)
    assert d.issued() == []  # Allocated but no first ACT, no active-buffer entry.
    finish(d, 1, offset=6)
    d.advance(66)
    assert d.issued() == [] and d.held() == 1
    d.advance(67)
    assert [(e["command"], e["clk"]) for e in d.issued()] == [("ACT_MOV", 67)]
    assert d.held() == 0
    timeline, total = MOVES[name]
    d.advance(67+total)
    assert [e["clk"]-67 for e in d.issued()] == timeline
    assert [e["depart"] for e in d.completions()] == [67, 67+total]


@pytest.mark.parametrize("name", MOVES)
@pytest.mark.parametrize("promotion_capacity", [0, 32])
def test_movement_blocks_compute_and_unrelated_close_through_recovery(name, promotion_capacity):
    d, r = fixture()
    d.capacity(promotion_capacity)
    d.movement(movement(r, name), 1)
    d.advance(1)
    candidate = compute(r, mats=(8, 8))  # Same mat, different rows.
    timeline, total = MOVES[name]
    for clk in [1, 2, timeline[-1]+1, total]:
        d.advance(clk)
        assert not d.start(candidate)
        assert not d.add(candidate.copy(), 2)
        assert not d.probe("PREpb", "PREpb", addr())["issue"]
    d.advance(total+1)
    assert d.start(candidate) and d.add(candidate, 2)
    assert [e["clk"]-1 for e in d.issued()] == timeline


@pytest.mark.parametrize("name", MOVES)
@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
def test_movement_continuation_survives_promotion_backpressure_and_priority_arrival(name, scheduler):
    d, r = fixture(scheduler)
    d.capacity(0)
    d.movement(movement(r, name), 1)
    d.advance(1)
    d.priority("REFab", scope())
    timeline, total = MOVES[name]
    d.advance(total)
    assert [e["clk"]-1 for e in d.issued()] == timeline
    d.advance(total+1)
    assert (d.issued()[-1]["command"], d.issued()[-1]["clk"]) == ("REFab", total+1)


def test_conventional_preab_recovery_blocks_reservation():
    d, r = fixture()
    d.raw("PREab", scope(), True)
    candidate = compute(r)
    d.advance(15)
    assert not d.start(candidate) and not d.add(candidate.copy(), 1)
    d.advance(16)
    assert d.add(candidate, 1)


@pytest.mark.parametrize("first,second", list(itertools.product(MOVES, repeat=2)))
@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
def test_all_movement_pairs_serialize_intersecting_mats(first, second, scheduler):
    d, r = fixture(scheduler)
    d.movement(movement(r, first, mat=0), 1)
    d.movement(movement(r, second, mat=0), 2)
    d.advance(300)
    first_events = [e["clk"] for e in d.issued() if e["source_id"] == 1]
    second_events = [e["clk"] for e in d.issued() if e["source_id"] == 2]
    assert [t-1 for t in first_events] == MOVES[first][0]
    assert second_events[0] == 1+MOVES[first][1]
    assert [t-second_events[0] for t in second_events] == MOVES[second][0]
    assert [e["depart"] for e in d.completions()] == [1+MOVES[first][1],
                                                                  1+MOVES[first][1]+MOVES[second][1]]


@pytest.mark.parametrize("first,second", list(itertools.product(MOVES, repeat=2)))
def test_other_bank_movement_progresses_during_local_gaps(first, second):
    d, r = fixture()
    d.movement(movement(r, first), 1)
    d.movement(movement(r, second, bank=1), 2)
    d.advance(300)
    starts = [e for e in d.issued() if e["command"] == "ACT_MOV"][:2]
    assert [e["source_id"] for e in starts] == ([1, 1] if first == "GB-MOV" else [1, 2])
    other = next(e for e in d.issued() if e["source_id"] == 2)
    assert other["clk"] < MOVES[first][0][-1]+1
    assert len({e["clk"] for e in d.issued()}) == len(d.issued())


@pytest.mark.parametrize("name", MOVES)
def test_movement_validity_and_endpoint_identity_are_retained(name):
    d, r = fixture()
    original = movement(r, name)
    locations = original.snapshot()["locations"]
    external = original.snapshot()["external"]
    located = _located_lifetime(original.copy(), dram_config())
    d.movement(original, 1)
    timeline, total = MOVES[name]
    expected = ([(True, False, False), (True, False, True), (False, False, True),
                 (False, True, True), (False, True, False), (False, False, False)]
                if name == "LC-MOV" else
                [(True, False, False), (True, True, False), (True, True, True),
                 (True, True, False), (False, False, False)])
    for index, (clk, state) in enumerate(zip(timeline, expected)):
        d.advance(clk+1)
        observed = d.movement_state(1)
        assert tuple(observed[k] for k in ("source_active", "destination_active", "source_valid")) == state
        assert observed["external"] == external
        paired = located["movement_states"][index]
        assert paired["same_bundle"] and paired["locations"] == locations
        assert tuple(paired[k] for k in ("source_active", "destination_active", "source_valid")) == state
        assert observed["cursor"] == index+1
        assert observed["sequence_active"] == (index+1 != len(timeline))
        # Both source PRE recovery and terminal recovery preserve identity.
        d.advance(min(clk+2, total))
        assert d.movement_state(1)["external"] == external
    d.advance(total+1)
    event, = d.completions()
    assert event["external"] == external and not event["source_valid"]
    assert located["completion"]["locations"] == locations
    stats = d.stats()
    key = "lcmov" if name == "LC-MOV" else "gbmov"
    assert stats[f"pud_{key}_moved_bits"] == 4


@pytest.mark.parametrize("auto,delay", [("RDA", 25), ("WRA", 50)])
def test_ordinary_autoprecharge_recovery_blocks_compute_start(auto, delay):
    d, r = fixture()
    candidate = compute(r)
    d.raw("ACT", addr(), True)
    assert not d.start(candidate) and not d.add(candidate.copy(), 1)
    d.advance(39)
    d.raw(auto, addr(), True)
    assert not d.start(candidate) and not d.add(candidate.copy(), 1)
    d.advance(39+delay-1)
    assert not d.start(candidate)
    d.advance(39+delay)
    assert d.start(candidate) and d.add(candidate, 1)


def test_ordinary_active_work_and_conventional_preparation_drain_before_reservation():
    d, r = fixture()
    d.send(0, addr(), 2)
    d.advance(1)  # ACT issued; ordinary request still active.
    candidate = compute(r)
    assert not d.start(candidate) and not d.add(candidate.copy(), 1)
    d.advance(40)  # Read completed, conventional Bank remains open.
    assert not d.start(candidate)
    before = candidate.snapshot()
    assert d.probe("ACT_PUD_S_OC", "PREpb", addr())["preq"] == "PREpb"
    d.priority("PREpb", addr())
    d.advance(41)
    assert candidate.snapshot() == before
    d.advance(56)
    assert not d.start(candidate)
    d.advance(57)
    assert d.add(candidate, 1)


@pytest.mark.parametrize("command", ["PREab", "REFab"])
@pytest.mark.parametrize("arrival", [0, 1, 12, 51])
def test_priority_maintenance_waits_for_last_recovery_before_whole_scope_action(command, arrival):
    d, r = fixture()
    # Earlier Bank is Opened: a later conflict must prevent partial PRE/action/history updates.
    d.raw("ACT", addr(0), True)
    assert d.add(compute(r, "MAJ3", bank=2), 1)
    assert d.add(compute(r, "NOT", bank=3, bg=3), 2)
    # The ordinary ACT at zero occupies the shared command cycle.
    events = sorted([(clk+1, 1) for clk in TIMELINES["MAJ3"]] +
                    [(clk+2, 2) for clk in TIMELINES["NOT"]])
    queued = False
    for clk, source in events:
        if not queued and arrival <= clk:
            d.advance(arrival)
            d.priority(command, scope())
            queued = True
        d.dispatch(source, clk)
    d.advance(100)
    assert d.issued() == []  # Last recovery is NOT at 101, even though MAJ3 drained at 67.
    before = d.shared()
    for raw_command in ("PREab", "REFab"):
        with pytest.raises(RuntimeError, match="protected PuD invocation"):
            d.raw(raw_command, scope(), True)
        assert d.shared() == before
    d.advance(101)
    assert [(e["command"], e["clk"]) for e in d.issued()] == [("PREab", 101)]
    assert d.held() == 0
    if command == "REFab":
        d.advance(116)
        assert len(d.issued()) == 1
        d.advance(117)
        assert d.issued()[-1]["command"] == "REFab"


def test_no_redundant_preab_after_compute_only_drain():
    d, r = fixture()
    assert d.add(compute(r), 1)
    d.priority("REFab", scope())
    finish(d, 1)
    d.advance(60)
    assert d.issued() == []
    d.advance(61)
    assert [e["command"] for e in d.issued()] == ["REFab"]


def test_queued_maintenance_and_active_nrfc_block_start_but_other_rank_is_legal():
    d, r = fixture(ranks=4, nRFC=20)
    candidate = compute(r)
    d.priority("REFab", scope())
    assert not d.start(candidate) and not d.add(candidate.copy(), 1)
    d.advance(1)
    assert d.issued()[0]["command"] == "REFab"
    assert not d.start(candidate) and not d.add(candidate.copy(), 1)
    assert d.add(compute(r, rank=1), 2)
    d.priority("REFab", scope(2))
    d.advance(2)
    assert d.issued()[-1]["addr_vec"][1] == 2
    d.advance(20)
    assert not d.start(candidate)
    d.advance(21)
    assert d.add(candidate, 1)


def test_fifo_head_prevents_other_rank_bypass_and_new_reservations():
    d, r = fixture(ranks=4)
    assert d.add(compute(r), 1)
    d.priority("REFab", scope())
    d.priority("REFab", scope(1))
    assert not d.add(compute(r, rank=2), 2)
    finish(d, 1)
    d.advance(60)
    assert d.issued() == []
    d.advance(62)
    assert [e["addr_vec"][1] for e in d.issued()] == [0, 1]


@pytest.mark.parametrize("name", ["RowCopy", "MAJ3", "NOT_COPY"])
def test_disjoint_compute_continues_during_other_range_recovery(name):
    d, r = fixture()
    assert d.add(compute(r), 1)
    assert d.add(compute(r, name, mats=(1, 1)), 2)
    events = sorted([(clk, 1) for clk in TIMELINES["RowCopy"]] +
                    [(clk+2, 2) for clk in TIMELINES[name]])
    for clk, source in events:
        d.dispatch(source, clk)
    d.advance(max(61, TOTALS[name]+2))
    assert d.held() == 0 and len(d.completions()) == 2


@pytest.mark.parametrize("policy", ["Open", "ClosedCAP"])
@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
def test_ordinary_queue_and_rowpolicy_commands_cannot_repair_protected_bank(policy, scheduler):
    d, r = fixture(scheduler, policy=policy)
    assert d.add(compute(r), 1)
    d.send(0, addr(), 2)
    d.send(0, addr(1), 3)
    d.advance(20)
    assert all(e["source_id"] != 2 for e in d.issued())
    # Explicit plugin/policy-style queued close must remain a conventional Bank close.
    d.priority("PREpb", addr())
    finish(d, 1, offset=21)
    d.advance(81)
    assert not any(e["source_id"] == -2 for e in d.issued())
    d.advance(82)
    assert d.issued()[-1]["command"] == "PREpb"
    d.advance(160)
    assert any(e["source_id"] == 2 and e["command"] == "RD" for e in d.issued())


def test_final_recheck_catches_command_scope_upgrade():
    d, r = fixture()
    d.raw("ACT", addr(0), True)
    assert d.add(compute(r, bank=3), 1)
    d.advance(40)
    assert d.probe("RD", "RD", addr())["issue"]
    # An upgraded command can have a broader effective scope than final_command.
    assert not d.probe("REFab", "PREab", scope())["issue"]
    assert not d.probe("RD", "RDA", addr(3))["issue"]


def test_selection_then_compute_reservation_rechecks_ordinary_issue():
    d, r = fixture()
    assert d.probe("RD", "ACT", addr())["issue"]
    assert d.add(compute(r), 1)
    before = d.shared()
    assert not d.probe("RD", "ACT", addr())["issue"]
    assert d.shared() == before


@pytest.mark.parametrize("name,offset", [("RowCopy", 65), ("NOT", 0), ("MAJ5", 0)])
def test_allbank_generated_refresh_drains_allocated_active_and_recovering_compute(name, offset):
    d, r = fixture(refresh=True, nREFI=64, nRFC=2)
    assert d.add(compute(r, name), 1)
    finish(d, 1, name, offset)
    ready = TOTALS[name]+offset
    d.advance(ready-1)
    assert d.issued() == []
    d.advance(ready)
    assert [(e["command"], e["clk"]) for e in d.issued()] == [("REFab", ready)]


def test_forwarding_and_coalescing_still_happen_while_device_issue_is_blocked():
    d, r = fixture()
    assert d.add(compute(r), 1)
    d.send(1, addr(), 2)
    d.send(1, addr(), 3)
    d.send(0, addr(), 4)
    d.advance(1)
    assert d.issued() == []
    stats = d.stats()
    assert stats["num_read_reqs_forwarded"] == 1
    assert stats["num_write_reqs_coalesced"] == 1
