import pytest
import itertools
from tests.gddr7_pud import system, request, timeline, COMMANDS, events, times


@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
@pytest.mark.parametrize("name", list(COMMANDS)[:5])
@pytest.mark.parametrize("mats", [(0, 0), (15, 16), (0, 31)])
def test_public_compute_and_exact_once_recovery(scheduler, name, mats):
    d = system(scheduler)
    assert d.submit(request(d, name, mats), 0)
    commands, clocks, done = timeline(name)
    d.advance(done)
    assert d.completions() == [] and d.scheduling()["held"] == 1
    d.advance(done+1)
    assert times(d, 0) == [1+t for t in clocks]
    assert [e["command"] for e in events(d, 0)] == commands
    assert len(d.completions()) == 1 and d.completions()[0]["depart"] == done+1
    assert d.scheduling()["held"] == 0
    d.advance(done+100)
    assert len(d.completions()) == 1


@pytest.mark.parametrize("mode", ["always_on", "start_with_read", "start_with_rckstrt"])
@pytest.mark.parametrize("name", ["LC-MOV", "GB-MOV"])
@pytest.mark.parametrize("mat", [0, 15, 30])
def test_movement_exact_completion_without_external_rck(mode, name, mat):
    d = system(mode=mode)
    assert d.submit(request(d, name, mats=(mat, mat)), 0)
    commands, clocks, done = timeline(name)
    d.advance(done)
    assert d.completions() == [] and d.scheduling()["held"] == 1
    d.advance(done+1)
    assert times(d, 0) == [1+t for t in clocks]
    assert [e["command"] for e in events(d, 0)] == commands
    assert d.completions()[0]["depart"] == done+1
    d.advance(done+100)
    assert len(d.completions()) == 1 and d.scheduling()["held"] == 0
    assert not any(e["command"].startswith("RCK") for e in d.issued())


@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
@pytest.mark.parametrize("first,second", list(itertools.product(COMMANDS, repeat=2)))
@pytest.mark.parametrize("relation", ["disjoint", "intersect", "other_bank", "no_salp"])
def test_all_primitive_footprint_pairs(scheduler, first, second, relation):
    d = system(scheduler)
    assert d.submit(request(d, first), 0)
    assert d.submit(request(d, second,
        mats=(4, 4) if relation in ("disjoint", "no_salp") else (0, 0),
        bank=1 if relation == "other_bank" else 0,
        row=522 if relation == "no_salp" else 40), 1)
    d.advance(700)
    done = {e["source_id"]: e["depart"] for e in d.completions()}
    assert len(d.completions()) == 2 and d.scheduling()["held"] == 0
    starts = [times(d, i)[0] for i in range(2)]
    for i, name in enumerate((first, second)):
        assert [e["command"] for e in events(d, i)] == COMMANDS[name]
        assert done[i] == times(d, i)[-1]+30
    if relation in ("disjoint", "other_bank"):
        assert max(starts) < min(done.values())
    else:
        leader = starts.index(min(starts))
        assert starts[1-leader] >= done[leader]


@pytest.mark.parametrize("scheduler", ["FRFCFS", "FRFCFS-RowHit"])
@pytest.mark.parametrize("different_banks", [False, True])
def test_twelve_disjoint_compute_have_no_finite_engine_limit(scheduler, different_banks):
    d = system(scheduler)
    for i in range(12):
        assert d.submit(request(d, "NOT", mats=(0, 0) if different_banks else (i, i),
                                bank=i if different_banks else 0), i)
    d.advance(1)
    assert d.scheduling()["held"] == 12
    d.advance(24)
    assert [times(d, i) for i in range(12)] == [[1+2*i] for i in range(12)]
    assert d.completions() == []
    d.advance(400)
    assert len(d.completions()) == 12 and d.scheduling()["held"] == 0


def test_actual_row_and_column_issue_in_same_tick():
    d = system()
    assert d.submit(request(d, "LC-MOV"), 0)
    d.advance(30)
    assert d.submit(request(d, "NOT", bank=1), 1)
    d.advance(31)
    assert [(e["command"], e["clk"]) for e in d.issued()[-2:]] == [("RD_MOV", 31), ("ACT_PUD_S_OC", 31)]


@pytest.mark.parametrize("name", COMMANDS)
def test_dependent_reentrant_callback_waits_for_full_recovery(name):
    d = system()
    accepted = []
    def next_request(done):
        assert done["held"] == 0
        accepted.append(d.submit(request(d, name), 1))
    assert d.submit(request(d, name), 0, next_request)
    _, _, complete = timeline(name)
    d.advance(complete)
    assert accepted == []
    d.advance(complete+1)
    assert accepted == [True]
    assert times(d, 1)[0] == complete+1
    d.advance(1000)
    assert len(d.completions()) == 2 and d.scheduling()["held"] == 0


@pytest.mark.parametrize("mode", ["always_on", "start_with_read", "start_with_rckstrt"])
def test_internal_movement_and_external_read_retain_ordinary_rck_behavior(mode):
    d = system(mode=mode, rck_idle_threshold=4)
    assert d.submit(request(d, "LC-MOV"), 0)
    assert d.submit_ordinary(2048, 0, 1)  # Provisional map: Bank 1.
    d.advance(350)
    assert len(d.completions()) == 2
    cmds = [e["command"] for e in d.issued()]
    assert cmds.count("RD") == 1 and cmds.count("RD_MOV") == 1
    assert cmds.count("RCKSTRT") == (1 if mode == "start_with_rckstrt" else 0)
    assert cmds.count("RCKSTOP") == (0 if mode == "always_on" else 1)
    if mode != "always_on":
        read_clk = next(e["clk"] for e in d.issued() if e["command"] == "RD")
        stop_clk = next(e["clk"] for e in d.issued() if e["command"] == "RCKSTOP")
        assert stop_clk >= read_clk+18
    columns = [e for e in d.issued() if e["command"] in ("RD", "RD_MOV", "WR_MOV", "RCKSTRT", "RCKSTOP")]
    assert all(b["clk"]-a["clk"] >= 2 for a, b in zip(columns, columns[1:]))
