"""REF is evaluated; injected RFM cases assert structural safety only."""
import pytest
from tests.gddr7_pud import system, request, timeline, COMMANDS, events, times

MAINTENANCE = ["PREpb", "PREab", "REFpb", "REFab", "RFMpb", "RFMab"]


@pytest.mark.parametrize("name", COMMANDS)
@pytest.mark.parametrize("command", MAINTENANCE)
@pytest.mark.parametrize("phase", ["active", "recovering"])
def test_intersecting_maintenance_waits_through_recovery(name, command, phase):
    d = system()
    assert d.submit(request(d, name), 0)
    done = 1+timeline(name)[2]
    d.advance(5 if phase == "active" else done-10)
    address = [0, -1, -1, -1] if command.endswith("ab") else [0, 0, 0, 0]
    assert not d.ready(command, address)
    assert d.priority(command, address)
    d.advance(done-1)
    assert not d.ready(command, address)
    assert len(d.issued()) == len(COMMANDS[name])
    assert d.completions() == []
    d.advance(done)
    assert d.issued()[-1]["command"] == command and d.issued()[-1]["clk"] == done
    assert len(d.completions()) == 1 and d.scheduling()["held"] == 0


@pytest.mark.parametrize("command", MAINTENANCE)
def test_pre_act_reservations_protect_complete_maintenance_scope(command):
    d = system()
    assert d.submit(request(d, "NOT", (0, 0)), 0)
    assert d.submit(request(d, "NOT", (1, 1)), 1)
    d.advance(1)
    assert d.scheduling()["held"] == 2 and times(d, 1) == []
    address = [0, -1, -1, -1] if command.endswith("ab") else [0, 0, 0, 0]
    assert not d.ready(command, address)
    assert d.priority(command, address)
    d.advance(153)
    assert d.scheduling()["held"] == 1
    assert not d.ready(command, address)
    d.advance(154)
    assert d.issued()[-1]["command"] == command and d.issued()[-1]["clk"] == 154
    assert len(d.completions()) == 2


@pytest.mark.parametrize("name", ["NOT", "LC-MOV", "GB-MOV"])
@pytest.mark.parametrize("command", ["PREpb", "REFpb", "RFMpb"])
def test_per_bank_maintenance_can_progress_in_a_disjoint_bank(name, command):
    d = system()
    assert d.submit(request(d, name), 0)
    d.advance(5)
    assert d.priority(command, [0, 1, 0, 0])
    d.advance(6)
    assert d.issued()[-1]["command"] == command
    assert d.scheduling()["held"] == 1
    d.advance(1000)
    assert len(d.completions()) == 1


def test_priority_cannot_strand_acquired_movement_under_promotion_pressure():
    d = system()
    for i in range(20):
        assert d.submit(request(d, "LC-MOV", mats=(i, i)), i)
    d.advance(50)
    assert d.scheduling()["held"] == 20
    assert d.scheduling()["active_size"] == 16
    assert d.priority("REFab", [0, -1, -1, -1])
    d.advance(1000)
    assert len(d.completions()) == 20 and d.scheduling()["held"] == 0
    last = max(e["depart"] for e in d.completions())
    assert [(e["clk"], e["command"]) for e in d.issued() if e["command"] == "REFab"] == [(last, "REFab")]


@pytest.mark.parametrize("manager", ["AllBank", "PerBank"])
def test_evaluation_refresh_traces_contain_zero_rfm(manager):
    # Fixed accepted baseline, no timing overrides, no RFM plugin or injection.
    d = system(refresh=manager)
    for i, name in enumerate(COMMANDS):
        assert d.submit(request(d, name, bank=i), i)
    d.advance(7000)
    assert len(d.completions()) == 7
    cmds = [e["command"] for e in d.issued()]
    assert any(c.startswith("REF") for c in cmds)
    assert not any(c.startswith("RFM") for c in cmds)


@pytest.mark.parametrize("name", ["NOT", "LC-MOV", "GB-MOV"])
@pytest.mark.parametrize("access", ["ACT", "RD", "WR", "RDA", "WRA"])
def test_conventional_state_and_access_recovery_before_pud(name, access):
    d = system()
    address = [0, 0, 0, 0]
    assert d.priority("ACT", address)
    d.advance(100)
    if access != "ACT":
        assert d.priority(access, address)
        d.advance(101)
    assert d.submit(request(d, name), 0)
    d.advance(600)
    # AP closes state at issue; its recovery must still delay the first PuD ACT.
    # Otherwise a real conventional preparatory PRE drains the Bank first.
    if access in ("RDA", "WRA"):
        expected = 101 + (34 if access == "RDA" else 68)
    else:
        pre = next(e["clk"] for e in events(d, 0) if e["command"] == "PREpb")
        assert pre == {"ACT": 101, "RD": 106, "WR": 140}[access]
        expected = pre+29
    first = next(e["clk"] for e in events(d, 0) if e["command"] in ("ACT_PUD_S_OC", "ACT_MOV"))
    assert first == expected
    assert len(d.completions()) == 1


@pytest.mark.parametrize("name", COMMANDS)
def test_closedcap_ordinary_access_still_waits_for_pud_recovery(name):
    from ramulator._ramulator_test import _LocatedSystemUnderTest
    from tests.gddr7_pud import controller_config, resolver
    cfg = controller_config()
    cfg["row_policy"] = dict(impl="ClosedCAP", cap=1)
    d = _LocatedSystemUnderTest(cfg, resolver(), install=False)
    assert d.submit(request(d, name), 0)
    d.advance(1)
    assert d.submit_ordinary(0, 0, 1)
    done = 1+timeline(name)[2]
    d.advance(done-1)
    assert events(d, 1) == []
    d.advance(1000)
    assert len(d.completions()) == 2
    assert events(d, 1)[0]["clk"] == done
    # The terminal PuD close resets CAP: this is the first column access.
    assert events(d, 1)[-1]["command"] == "RD"


@pytest.mark.parametrize("mode", ["always_on", "start_with_read", "start_with_rckstrt"])
@pytest.mark.parametrize("policy", ["Open", "ClosedCAP"])
def test_ordinary_row_policy_stream_matches_conventional_gddr7(mode, policy):
    import ramulator
    from ramulator._ramulator_test import _LocatedSystemUnderTest
    from tests.gddr7_pud import controller_config, resolver
    streams = []
    for pud in (False, True):
        cfg = controller_config(mode=mode)
        cfg["row_policy"] = dict(impl=policy, **({"cap": 1} if policy == "ClosedCAP" else {}))
        if not pud:
            cfg["dram"] = ramulator.dram.GDDR7(
                org_preset="GDDR7_16Gb_x8", timing_preset="GDDR7_28000_PAM3").to_config()
            cfg.pop("pud_placement_profile")
        d = _LocatedSystemUnderTest(cfg, resolver(), install=False)
        assert d.priority("ACT", [0, 1, 0, 0])
        d.advance(30)
        assert d.submit_ordinary(0, 0, 1)
        d.advance(58)
        assert d.submit_ordinary(2048, 1, 2)
        assert d.submit_ordinary(32, 1, 3)
        assert d.submit_ordinary(64, 1, 4)
        d.advance(200)
        streams.append((d.issued(), d.completions()))
    # Compatibility, not a liveness oracle: legacy ClosedCAP can strand the
    # active Read by upgrading WR to WRA. Fixing that conventional defect is
    # outside Phase 2; importing DDR4's extra post-upgrade guard changes it.
    assert streams[0] == streams[1]
