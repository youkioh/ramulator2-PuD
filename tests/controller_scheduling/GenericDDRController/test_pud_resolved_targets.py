"""W6 resolved-target baseline on GenericDDR with explicit protected contexts."""

import pytest

from ramulator._ramulator_test import _PuDConflictUnderTest
from tests.controller_scheduling.GenericDDRController.test_pud_conflicts import (
    addr, compute, fixture, movement, scope,
)
from tests.device_timings.test_pud_compute_ranges import COMMANDS, TIMELINES, TOTALS
from tests.unit_tests.test_pud_request_locations import (
    COMPUTE, controller, descriptor, request, synthetic,
)


def snapshot(d, *ids):
    return d.command_occupancy(), d.shared(), [d.compute_state(i) for i in ids], d.held()


def issue(d, source, clk):
    d.advance(clk)
    before = snapshot(d, source)
    for _ in range(3):
        assert d.compute_dispatch(source)
        assert snapshot(d, source) == before
    assert d.compute_dispatch(source, issue=True)


def blocked(d, source, clk):
    d.advance(clk)
    before = snapshot(d, source)
    for _ in range(3):
        assert not d.compute_dispatch(source)
        assert snapshot(d, source) == before
    with pytest.raises(RuntimeError, match="not ready"):
        d.compute_dispatch(source, issue=True)
    assert snapshot(d, source) == before


@pytest.mark.parametrize("name", COMPUTE)
@pytest.mark.parametrize("mats", [(0, 0), (15, 16), (0, 127)])
def test_resolved_occurrences_and_recovery_anchors(name, mats):
    d, r = fixture()
    assert d.add(compute(r, name, mats, row=21), 1, 0)
    for index, (clk, command) in enumerate(zip(TIMELINES[name], COMMANDS[name])):
        if index:
            blocked(d, 1, clk-1)
        state = d.compute_state(1)
        occurrence = state["occurrences"][index]
        assert occurrence["index"] == state["cursor"] == index
        assert occurrence["command"] == command and occurrence["associated"]
        assert occurrence["range"] == list(mats)
        assert occurrence["external"] == state["addr_vec"]
        assert occurrence["external"][4] == 21 + occurrence["operand"]
        assert occurrence["origin"][4:] == [0, 21 + occurrence["operand"]]
        assert occurrence["issued"] == -1
        issue(d, 1, clk)
        state = d.compute_state(1)
        assert state["occurrences"][index] == occurrence | {"issued": clk}
        assert state["history"] == TIMELINES[name][:index+1] + [-1]*(len(COMMANDS[name])-index-1)
        # Only the actual command occupies C/A; no extra activation cycle.
        assert d.command_occupancy()[0] == clk+1
    d.advance(TOTALS[name]-1)
    assert d.held() == 1 and d.completions() == []
    d.advance(TOTALS[name])
    assert d.held() == 0 and d.completions()[0]["depart"] == TOTALS[name]


@pytest.mark.parametrize("destinations", [2, 5, 32])
@pytest.mark.parametrize("mats", [(0, 0), (15, 16), (0, 127)])
def test_rowcopy_each_equal_range_retains_distinct_operand(destinations, mats):
    d, r = fixture()
    req = request(r, "RowCopy", [descriptor(10+i, mats) for i in range(destinations+1)])
    assert d.add(req.copy(), 1, 0)
    for index, clk in enumerate([0] + [40+5*i for i in range(destinations+1)]):
        before = d.compute_state(1)
        occurrence = before["occurrences"][index]
        assert occurrence["operand"] == min(index, destinations)
        assert occurrence["external"][4] == 10 + min(index, destinations)
        assert occurrence["range"] == list(mats) and occurrence["associated"]
        issue(d, 1, clk)  # Fixture relocates the sole Request after each action.
    d.advance(40+5*destinations+16)
    assert d.held() == 0


@pytest.mark.parametrize("mats", [(0, 0), (15, 16)])
def test_many_explicit_reservations_have_no_per_chip_issue_order_or_capacity(mats):
    d, r = fixture()
    # Explicit fixture engines, not a production allocation policy or E default.
    for i in range(12):
        assert d.add(compute(r, "NOT", mats, bank=i % 4, bg=i // 4), i, i)
    for clk, i in enumerate(reversed(range(12))):
        issue(d, i, clk)
    assert d.held() == 12
    for clk, i in enumerate(reversed(range(12))):
        issue(d, i, 40+clk)
    for clk, i in enumerate(reversed(range(12))):
        issue(d, i, 83+clk)
    d.advance(110)
    assert d.held() == 0 and len(d.completions()) == 12


@pytest.mark.parametrize("late", [0, 37])
@pytest.mark.parametrize("preceding_pre", [False, True])
def test_cold_and_late_activation_issue_as_soon_as_ordinary_recovery_allows(late, preceding_pre):
    d, r = fixture()
    if preceding_pre:
        d.raw("PREpb", addr(), True)
    clk = (16 if preceding_pre else 0) + late
    d.advance(clk)
    assert d.add(compute(r, "NOT"), 1, 0)
    issue(d, 1, clk)
    assert d.compute_state(1)["history"] == [clk, -1, -1]


@pytest.mark.parametrize("command", ["ACT", "ACT_MOV"])
def test_actual_compute_cycle_blocks_other_bank_but_next_cycle_is_free(command):
    d, r = fixture()
    assert d.add(compute(r), 1, 0)
    issue(d, 1, 0)
    before = snapshot(d, 1)
    assert not d.probe(command, command, addr(bank=1))["issue"]
    with pytest.raises(RuntimeError, match="C/A occupied"):
        d.raw(command, addr(bank=1), True)
    assert snapshot(d, 1) == before
    d.advance(1)
    assert d.probe(command, command, addr(bank=1))["issue"]
    d.raw(command, addr(bank=1), True)


@pytest.mark.parametrize("command", ["ACT", "ACT_MOV"])
def test_ordinary_or_movement_command_cycle_blocks_compute_without_mutation(command):
    d, r = fixture()
    assert d.add(compute(r), 1, 0)
    d.raw(command, addr(bank=1), True)
    blocked(d, 1, 0)
    issue(d, 1, 1)


@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
def test_scheduled_ordinary_command_issues_next_cycle(scheduler):
    d, r = fixture(scheduler)
    assert d.add(compute(r), 1, 0)
    issue(d, 1, 0)
    d.send(0, addr(bank=1), 2)
    d.advance(1)
    assert [(e["command"], e["clk"]) for e in d.issued()] == [("ACT", 1)]


@pytest.mark.parametrize("name", ["LC-MOV", "GB-MOV"])
@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
def test_scheduled_movement_issues_next_cycle_and_preserves_local_anchor(name, scheduler):
    d, r = fixture(scheduler)
    assert d.add(compute(r), 1, 0)
    issue(d, 1, 0)
    d.movement(movement(r, name, bank=1), 2)
    d.advance(1)
    assert [(e["command"], e["clk"]) for e in d.issued()] == [("ACT_MOV", 1)]
    # LC issues its source PRE at 40; compute must respect that actual cycle.
    if name == "LC-MOV":
        blocked(d, 1, 40)
    issue(d, 1, 41)
    issue(d, 1, 46)
    total = 130 if name == "LC-MOV" else 75
    d.advance(1+total)
    event = next(e for e in d.completions() if e["source"] == 2)
    assert event["depart"] == 1+total


@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
def test_allocated_ranges_drain_after_maintenance_arrives_before_first_act(scheduler):
    d, r = fixture(scheduler)
    for i, mats in enumerate([(14, 15), (15, 16), (16, 17)]):
        assert d.add(compute(r, mats=mats, bank=i), i, i)
    d.priority("REFab", scope())
    assert not d.start(compute(r, bank=3))
    for offset in (0, 40, 45):
        for i in range(3):
            issue(d, i, offset+i)
    d.advance(62)
    assert not d.issued() and d.held() == 1
    d.advance(63)
    assert d.held() == 0 and [e["command"] for e in d.issued()] == ["REFab"]


def test_replacement_profile_supplies_resolved_row_and_chip_segments_across_n():
    r, config = synthetic()
    d = _PuDConflictUnderTest(controller(config, mapper="PassThroughAddrMapper"))
    assert d.add(compute(r, "NOT_COPY", (7, 8), row=1022), 1, 0)
    for index, clk in enumerate(TIMELINES["NOT_COPY"]):
        occurrence = d.compute_state(1)["occurrences"][index]
        assert occurrence["range"] == [7, 8]
        assert occurrence["segments"] == [[0, 7, 7], [1, 0, 0]]
        assert occurrence["associated"]
        assert occurrence["external"][4] == 1022 + (index >= 2)
        issue(d, 1, clk)
    d.advance(104)
    assert d.held() == 0


def test_unallocated_and_released_associations_cannot_issue():
    d, r = fixture()
    before = snapshot(d)
    for mutate in (False, True):
        with pytest.raises(RuntimeError, match="protected compute context"):
            d.unallocated_dispatch(compute(r), mutate)
        assert snapshot(d) == before
    assert d.add(compute(r), 1, 0)
    for clk in TIMELINES["RowCopy"]:
        issue(d, 1, clk)
    d.advance(61)
    before = snapshot(d, 1)
    for mutate in (False, True):
        with pytest.raises(RuntimeError, match="protected compute context"):
            d.compute_dispatch(1, issue=mutate)
        assert snapshot(d, 1) == before


def test_disjoint_activation_after_range_pre_keeps_close_and_target_independent():
    d, r = fixture()
    assert d.add(compute(r, mats=(0, 0)), 1, 0)
    assert d.add(compute(r, "NOT_COPY", (1, 1), row=30), 2, 1)
    for clk in TIMELINES["RowCopy"]:
        issue(d, 1, clk)
    before = d.compute_state(1)
    blocked(d, 2, 45)
    issue(d, 2, 46)
    assert d.compute_state(1) == before
    assert d.compute_state(2)["occurrences"][0]["external"][4] == 30
    d.advance(61)
    assert d.completions()[0]["depart"] == 61

@pytest.mark.parametrize("command", ["ACT", "ACT_MOV", "ACT_PUD_S_OC"])
def test_shared_deadline_honors_actual_command_cycles(command):
    from ramulator.dram import DDR4_PuD_Movement as Standard
    from tests.unit_tests.test_pud_location import dram_config, resolver

    config = dram_config()
    # Synthetic occupancy-only probe of the existing command_cycles field.
    # This does not define a new production timing profile or shift PRADA edges.
    config["command_cycles"][Standard.commands.index(command)] = 3
    d = _PuDConflictUnderTest(controller(config, mapper="PassThroughAddrMapper"))
    r = resolver(config=config)
    assert d.add(compute(r, "NOT", (0, 0)), 1, 0)
    assert d.add(compute(r, "MAJ3", (1, 1)), 2, 1)
    if command == "ACT_PUD_S_OC":
        issue(d, 1, 0)
    else:
        d.raw(command, addr(bank=1), True)
    for clk in (0, 1, 2):
        blocked(d, 2, clk)
        if command == "ACT_PUD_S_OC":
            assert not d.probe("ACT", "ACT", addr(bank=1))["issue"]
    issue(d, 2, 3)
