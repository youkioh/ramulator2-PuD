"""W3 range-local Device components; explicit contexts, no public v2 path."""

from decimal import Decimal, ROUND_CEILING

import pytest

from ramulator._ramulator_test import _ComputeRangesUnderTest
from tests.unit_tests.test_pud_location import dram_config, resolver
from tests.unit_tests.test_pud_request_locations import COMPUTE, descriptor, request, synthetic


# Exact accepted occurrence clocks, first ACT at zero, through terminal PRE.
TIMELINES = {
    "RowCopy": [0, 40, 45],
    "MAJ3": [0, 11, 16, 50],
    "MAJ5": [0, 11, 16, 21, 26, 60],
    "NOT": [0, 40, 83],
    "NOT_COPY": [0, 40, 83, 88],
}
TOTALS = dict(RowCopy=61, MAJ3=66, MAJ5=76, NOT=99, NOT_COPY=104)
COMMANDS = {
    "RowCopy": ["ACT_PUD_S_OC", "ACT_PUD", "PREpb"],
    "MAJ3": ["ACT_PUD_OC", "ACT_PUD", "ACT_PUD_S", "PREpb"],
    "MAJ5": ["ACT_PUD_OC", "ACT_PUD", "ACT_PUD", "ACT_PUD", "ACT_PUD_S", "PREpb"],
    "NOT": ["ACT_PUD_S_OC", "N", "PREpb"],
    "NOT_COPY": ["ACT_PUD_S_OC", "N", "ACT_PUD", "PREpb"],
}


def add(d, r, name, mats=(0, 0), row=0, count=None):
    return d.add(request(r, name, [descriptor(row+i, mats)
                                 for i in range(count or COMPUTE[name])]))


def issue(d, i, clk, boundary=True):
    before = d.state(i), d.shared()
    if boundary and clk:
        assert not d.dispatch(i, clk-1)
        with pytest.raises(RuntimeError, match="timing not ready"):
            d.dispatch(i, clk-1, issue=True)
        assert (d.state(i), d.shared()) == before
    assert d.dispatch(i, clk)
    assert (d.state(i), d.shared()) == before
    d.dispatch(i, clk, issue=True)


@pytest.mark.parametrize("name", COMPUTE)
@pytest.mark.parametrize("mats", [(0, 0), (15, 16), (0, 127)])
def test_isolated_anchors_phases_rows_and_request_cursor(name, mats):
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    i = add(d, r, name, mats, row=21)
    shared = d.shared()
    expected_rows = []
    phase = "Closed"
    for index, (clk, command) in enumerate(zip(TIMELINES[name], COMMANDS[name])):
        assert d.state(i)["cursor"] == index
        issue(d, i, clk)
        if command.startswith("ACT"):
            operand = 1 if name == "NOT_COPY" and index == 2 else index
            expected_rows.append(21 + operand)
            if command == "ACT_PUD_OC": phase = "PuDChargeSharing"
            elif command in ("ACT_PUD_S", "ACT_PUD_S_OC"): phase = "PuDSensed"
        elif command == "PREpb":
            expected_rows = []
            phase = "Recovering"
        s = d.state(i)
        assert s["phase"] == phase
        assert [row[4] for row in s["activated_rows"]] == expected_rows
        assert s["cursor"] == index + 1 and s["same_bundle"]
        assert s["history"] == TIMELINES[name][:index+1] + [-1]*(len(TIMELINES[name])-index-1)
        # Every non-Channel state/history/deadline remains untouched.
        assert d.shared()[1:] == shared[1:]
    # Controller lifecycle tests enforce the terminal-PRE-to-depart boundary.


@pytest.mark.parametrize("destinations", [2, 5, 32])
@pytest.mark.parametrize("mats", [(0, 0), (15, 16), (0, 127)])
def test_multi_destination_rowcopy(destinations, mats):
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    i = add(d, r, "RowCopy", mats, count=destinations+1)
    for clk in [0] + [40+5*j for j in range(destinations+1)]:
        issue(d, i, clk)
    assert d.state(i)["cursor"] == destinations + 2
    assert d.state(i)["activated_rows"] == []


@pytest.mark.parametrize("names", [(n, n) for n in COMPUTE] +
                         [("NOT", "MAJ5"), ("NOT_COPY", "RowCopy"), ("MAJ3", "NOT_COPY")])
def test_independent_interleaving_and_range_close(names):
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    ids = [add(d, r, names[0], (0, 14), 11), add(d, r, names[1], (15, 31), 41)]
    # Staggered by two CK: N in one range can overlap activation, sensing,
    # and close in the other. Both sequences progress before either recovers.
    events = sorted((clk+2*i, i) for i, name in enumerate(names) for clk in TIMELINES[name])
    for clk, i in events:
        other = d.state(ids[1-i])
        issue(d, ids[i], clk, boundary=clk != 2)
        assert d.state(ids[1-i]) == other


def test_one_range_recovery_does_not_delay_new_disjoint_start():
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    a = add(d, r, "RowCopy", (0, 0))
    b = add(d, r, "NOT", (1, 1), 9)
    for clk in TIMELINES["RowCopy"]: issue(d, a, clk)
    recovering = d.state(a)
    issue(d, b, 46)  # Only shared C/A after PRE at 45, not Bank nRP until 61.
    assert d.state(a) == recovering
    assert d.state(b)["phase"] == "PuDSensed"


@pytest.mark.parametrize("issue_command", [False, True])
@pytest.mark.parametrize("bad", ["wrong_range", "null", "foreign", "command", "stale_occurrence"])
def test_rejected_dispatch_is_atomic(issue_command, bad):
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    a = add(d, r, "NOT_COPY", (0, 0))
    b = add(d, r, "NOT_COPY", (1, 1))
    saved = d.save(a)
    kwargs = {}
    if bad == "wrong_range": kwargs["context_id"] = b
    elif bad == "null": kwargs["context_id"] = -2
    elif bad == "foreign": kwargs["foreign_device"] = True
    elif bad == "command": kwargs["command"] = "PREpb"
    else:
        issue(d, a, 0)
        kwargs["saved_occurrence"] = saved
    before = d.state(a), d.state(b), d.shared()
    with pytest.raises(RuntimeError):
        d.dispatch(a, 100, issue=issue_command, **kwargs)
    assert (d.state(a), d.state(b), d.shared()) == before


@pytest.mark.parametrize("name", ["MAJ3", "MAJ5", "NOT", "NOT_COPY", "RowCopy"])
def test_charge_sharing_and_premature_pre_rejected(name):
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    a = add(d, r, name)
    issue(d, a, 0)
    before = d.state(a), d.shared()
    for command in ["PREpb", "ACT_PUD_OC"]:
        with pytest.raises(RuntimeError):
            d.dispatch(a, 100, command=command, issue=True)
        assert (d.state(a), d.shared()) == before


def test_device_does_not_follow_a_cursor_advanced_without_its_action():
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    a = add(d, r, "MAJ3")
    d.skip(a)  # Fabricated controller progress cannot establish charge sharing.
    before = d.state(a), d.shared()
    with pytest.raises(RuntimeError, match="Incompatible compute range phase"):
        d.dispatch(a, 200, issue=True)
    assert (d.state(a), d.shared()) == before


@pytest.mark.parametrize("predecessor,ready", [("PREpb", 16), ("PREab", 16),
                                             ("REFab", 433), ("RDA", 41), ("WRA", 66)])
@pytest.mark.parametrize("name", ["MAJ3", "NOT"])
def test_inherited_recovery_still_gates_starts(predecessor, ready, name):
    config = dram_config()
    d, r = _ComputeRangesUnderTest(config), resolver()
    addr = [0, 0, 0, 0, 0, 0]
    if predecessor in ("RDA", "WRA"):
        assert d.raw("ACT", addr, 0, issue=True)
        assert d.raw(predecessor, addr, 16, issue=True)
    else:
        target = [0, 0, -1, -1, -1, -1] if predecessor in ("PREab", "REFab") else addr
        assert d.raw(predecessor, target, 0, issue=True)
    a = add(d, r, name)
    issue(d, a, ready)


def test_shared_ca_with_ordinary_movement_and_other_range():
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    a = add(d, r, "NOT", (0, 0))
    b = add(d, r, "MAJ3", (1, 1))
    issue(d, a, 0)
    other_bank = [0, 0, 0, 1, 0, 0]
    assert not d.raw("ACT", other_bank, 0)
    assert not d.raw("ACT_MOV", other_bank, 0)
    assert d.raw("ACT", other_bank, 1)
    assert d.raw("ACT_MOV", other_bank, 1)
    issue(d, b, 1)
    # N has the same shared issue occupancy even though it adds no row identity.
    issue(d, a, 40)
    assert not d.raw("ACT", other_bank, 40)
    assert d.raw("ACT", other_bank, 41)


def test_compute_does_not_enter_ordinary_activation_current_history():
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    ids = [add(d, r, "NOT", (i, i)) for i in range(5)]
    for clk, i in enumerate(ids): issue(d, i, clk)
    assert d.raw("ACT", [0, 0, 0, 1, 0, 0], 5, issue=True)
    # Ordinary nRRDL=6 and nRRDS=4 remain in their original shared scopes.
    assert not d.raw("ACT", [0, 0, 0, 2, 0, 0], 10)
    assert d.raw("ACT", [0, 0, 0, 2, 0, 0], 11)
    assert not d.raw("ACT", [0, 0, 1, 0, 0, 0], 8)
    assert d.raw("ACT", [0, 0, 1, 0, 0, 0], 9)


def test_replacement_profile_uses_retained_rows_and_ranges():
    r, config = synthetic()
    d = _ComputeRangesUnderTest(config)
    a = add(d, r, "NOT_COPY", (7, 8), 1022)
    for clk in TIMELINES["NOT_COPY"]: issue(d, a, clk)
    assert d.state(a)["history"] == TIMELINES["NOT_COPY"]
    assert all(o["range"] == [7, 8] for o in d.state(a)["locations"])


@pytest.mark.parametrize("ns,cycles", [("9", 11), ("4", 5), ("32.992", 40), ("27.992", 34)])
def test_fine_grained_upper_envelope_does_not_add_cycles(ns, cycles):
    for scale in ("1", "1.005"):
        rounded = (Decimal(ns)*Decimal(scale)/Decimal("0.833")).to_integral_value(rounding=ROUND_CEILING)
        assert rounded == cycles


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("bad", ["wrong_range", "null", "wrong_operand", "wrong_role", "wrong_index", "terminal", "unassociated"])
def test_each_act_n_and_pre_keeps_exact_occurrence_association(index, bad):
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    a = add(d, r, "NOT_COPY", (15, 16), 40)
    # Even identical numerical locations do not identify the same invocation.
    b = add(d, r, "NOT_COPY", (15, 16), 40)
    for clk in TIMELINES["NOT_COPY"][:index]: issue(d, a, clk)
    saved = d.save(a)
    kwargs = dict(saved_occurrence=saved)
    if bad == "wrong_range": kwargs["context_id"] = b
    elif bad == "null": kwargs["context_id"] = -2
    else: d.corrupt_occurrence(saved, bad)
    before = d.state(a), d.state(b), d.shared()
    for mutate in (False, True):
        with pytest.raises(RuntimeError):
            d.dispatch(a, 200, issue=mutate, **kwargs)
        assert (d.state(a), d.state(b), d.shared()) == before


def test_stale_sensed_occurrence_cannot_repeat_n():
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    a = add(d, r, "NOT_COPY")
    issue(d, a, 0)
    saved = d.save(a)  # Sensed, N is next.
    issue(d, a, 40)   # Still sensed; occurrence must match the current Request.
    before = d.state(a), d.shared()
    with pytest.raises(RuntimeError, match="Wrong or stale compute occurrence"):
        d.dispatch(a, 100, saved_occurrence=saved, issue=True)
    assert (d.state(a), d.shared()) == before


def test_dispatch_preserves_explicit_shared_channel_edges():
    # A synthetic constraint verifies both full-hierarchy readiness and the
    # Channel-only update seam independently of the shared command occupancy.
    from ramulator.dram import DDR4_PuD_Movement as Standard
    config = dram_config()
    commands = {c: Standard.commands.index(c) for c in Standard.commands}
    config["timing_constraints"].append(
        [0, [commands["ACT_PUD_S_OC"]], [commands["ACT_PUD_OC"], commands["ACT"]], 7])
    d, r = _ComputeRangesUnderTest(config), resolver()
    a, b = add(d, r, "NOT", (0, 0)), add(d, r, "MAJ3", (1, 1))
    issue(d, a, 0)
    assert not d.raw("ACT", [0, 0, 0, 1, 0, 0], 6)
    assert d.raw("ACT", [0, 0, 0, 1, 0, 0], 7)
    issue(d, b, 7)


def test_outgoing_scope_inventory_matches_inherited_definitions():
    from ramulator.dram import DDR4_PuD_Movement as Standard
    compute = {"ACT_PUD_OC", "ACT_PUD", "ACT_PUD_S_OC", "ACT_PUD_S", "N"}
    actual = set()
    for edge in dram_config()["timing_constraints"]:
        level, previous, following, delay, *options = edge
        for p in previous:
            for f in following:
                if Standard.commands[p] in compute | {"PREpb"}:
                    assert not options or options == [1]
                    actual.add((list(Standard.levels)[level], Standard.commands[p], Standard.commands[f], delay))
    expected = {
        ("Bank", "ACT_PUD_OC", "ACT_PUD", 11),
        *(("Bank", "ACT_PUD", c, 5) for c in ("ACT_PUD", "ACT_PUD_S", "PREpb")),
        *(("Bank", "ACT_PUD_S_OC", c, 40) for c in ("ACT_PUD", "N")),
        ("Bank", "ACT_PUD_S", "PREpb", 34),
        *(("Bank", "N", c, 43) for c in ("ACT_PUD", "PREpb")),
        *(("Bank", "PREpb", c, 16) for c in ("ACT", "ACT_PUD_OC", "ACT_PUD_S_OC", "ACT_MOV")),
        ("Rank", "PREpb", "REFab", 16),
    }
    assert actual == expected


def test_context_requires_drained_conventional_rows():
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    addr = [0, 0, 0, 0, 77, 0]
    assert d.raw("ACT", addr, 0, issue=True)
    before = d.shared()
    with pytest.raises(RuntimeError, match="drained conventional Bank"):
        add(d, r, "NOT")
    assert d.shared() == before
    assert d.raw("PREpb", addr, 39, issue=True)
    a = add(d, r, "NOT")
    issue(d, a, 55)


def test_protected_context_rejects_conventional_row_activation():
    d, r = _ComputeRangesUnderTest(dram_config()), resolver()
    a = add(d, r, "NOT")
    before = d.state(a), d.shared()
    with pytest.raises(RuntimeError, match="protected compute context"):
        d.raw("ACT", [0, 0, 0, 0, 77, 0], 0, issue=True)
    assert (d.state(a), d.shared()) == before
    issue(d, a, 0)
