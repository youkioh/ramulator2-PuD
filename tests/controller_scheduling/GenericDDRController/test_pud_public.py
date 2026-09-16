"""W8: configured public Request -> GenericDRAM -> GenericDDR -> Device path."""

import pytest
import ramulator

from ramulator._ramulator_test import _LocatedSystemUnderTest, _bare_request
from ramulator.dram.spec import REQUEST_TYPE_IDS
from tests.unit_tests.test_pud_location import resolver, dram_config
from tests.unit_tests.test_pud_request_locations import controller, descriptor, COMPUTE
from tests.device_timings.test_pud_compute_ranges import TIMELINES, TOTALS

PROFILE = "MIMDRAM_DDR4_8Gb_x8_v1"
SCHEDULERS = ["FRFCFS", "FRFCFS-RowHit"]


def system(scheduler="FRFCFS", pending=32, refresh=False, **timing):
    cfg = controller(dram_config(**timing))
    cfg.update(pud_placement_profile=PROFILE, pud_buffer_size=pending)
    cfg["scheduler"]["impl"] = scheduler
    cfg["refresh_manager"]["impl"] = "AllBank" if refresh else "NoRefresh"
    return _LocatedSystemUnderTest(cfg, resolver(), install=False)


def request(d, name="RowCopy", mats=(15, 16), row=10, count=None, bank=0):
    movement = name in ("LC-MOV", "GB-MOV")
    descriptors = []
    for i in range(count or (2 if movement else COMPUTE[name])):
        selected = (6+i, 6+i) if name == "GB-MOV" else mats
        desc = descriptor(row+i, selected, i+3 if movement else None)
        desc["row"][3] = bank
        descriptors.append(desc)
    return d.request(REQUEST_TYPE_IDS[name], descriptors, -1 if movement else 64)


def events(d, source):
    return [e for e in d.issued() if e["source_id"] == source]


def times(d, source):
    return [e["clk"] for e in events(d, source)]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("name", TOTALS)
@pytest.mark.parametrize("mats", [(0, 0), (15, 16), (0, 127)])
def test_public_local_anchors_and_authoritative_locations(scheduler, name, mats):
    d = system(scheduler)
    req = request(d, name, mats)
    locations = req.snapshot()["locations"]
    assert d.submit(req, 0)
    assert d.scheduling()["held"] == 0  # Enqueue does not allocate.
    d.advance(1)
    assert d.scheduling()["held"] == 1
    assert d.scheduling()["active_size"] == 0
    d.advance(1 + TOTALS[name] - 1)
    assert d.scheduling()["held"] == 1 and d.completions() == []
    key = name.lower()
    stats = d.stats()
    assert stats[f"total_num_pud_{key}_requests"] == 1
    assert stats["controller"][f"num_pud_{key}_reqs"] == 1
    assert stats["controller"][f"num_pud_{key}_reqs_completed"] == 0
    assert stats["controller"][f"pud_{key}_latency"] == 0
    d.advance(1 + TOTALS[name])
    assert times(d, 0) == [t+1 for t in TIMELINES[name]]
    assert all(e["allocated"] and e["locations"] == locations for e in events(d, 0))
    done, = d.completions()
    assert done["locations"] == locations and done["held"] == 0
    assert done["depart"] == 1 + TOTALS[name]
    assert d.scheduling()["held"] == 0
    d.advance(120)
    stats = d.stats()["controller"]
    assert stats[f"num_pud_{key}_reqs_completed"] == 1
    assert stats[f"pud_{key}_latency"] == 1 + TOTALS[name]
    assert stats[f"avg_pud_{key}_latency"] == 1 + TOTALS[name]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("name", TOTALS)
def test_public_full_mat_tag_executes_identically_to_explicit_full_range(scheduler, name):
    explicit_system = system(scheduler)
    explicit = request(explicit_system, name, (0, 127))
    assert explicit_system.submit(explicit, 0)
    explicit_system.advance(160)

    tagged_system = system(scheduler)
    descriptors = [dict(kind="compute", row=[0, 0, 0, 0, 10+i], target="FULL_MAT")
                   for i in range(COMPUTE[name])]
    tagged = tagged_system.request(REQUEST_TYPE_IDS[name], descriptors, 64)
    assert tagged_system.submit(tagged, 0)
    tagged_system.advance(160)

    assert tagged.snapshot() == explicit.snapshot()
    assert times(tagged_system, 0) == times(explicit_system, 0)
    assert tagged_system.completions()[0]["depart"] == explicit_system.completions()[0]["depart"]


@pytest.mark.parametrize("destinations", [1, 2, 5, 17])
def test_public_multidestination_rowcopy(destinations):
    d = system()
    assert d.submit(request(d, count=destinations+1), 0)
    d.advance(1+40+5*destinations+16)
    assert times(d, 0) == [1] + [41+5*i for i in range(destinations+1)]
    assert d.completions()[0]["depart"] == 1+40+5*destinations+16


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("second", ["RowCopy", "NOT_COPY"])
def test_public_disjoint_overlap(scheduler, second):
    d = system(scheduler)
    assert d.submit(request(d), 0)
    assert d.submit(request(d, second, (17, 20)), 1)
    d.advance(1)
    state = d.scheduling()
    assert state["held"] == 2 and state["active_size"] == 0
    assert state["pending"][1]["history"] == [-1]*len(TIMELINES[second])
    assert state["pending"][1]["phase"] == 0
    d.advance(200)
    start = 2
    assert times(d, 0) == [1, 41, 46]
    assert times(d, 1) == [start+t for t in TIMELINES[second]]
    assert [e["depart"] for e in d.completions()] == [62, start+TOTALS[second]]
    assert len({e["clk"] for e in d.issued()}) == len(d.issued())


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_public_first_fit_and_more_than_eight_disjoint_invocations(scheduler):
    d = system(scheduler)
    for i in range(12):
        assert d.submit(request(d, "NOT", (i, i)), i)
    d.advance(1)
    state = d.scheduling()
    assert state["held"] == 12 and state["active_size"] == 0
    assert [r["phase"] for r in state["pending"]] == [2]+[0]*11
    d.advance(12)
    assert [times(d, i) for i in range(12)] == [[i+1] for i in range(12)]
    d.advance(99)
    assert d.scheduling()["held"] == 12 and d.completions() == []
    d.advance(250)
    assert len(d.completions()) == 12 and d.scheduling()["held"] == 0
    d = system(scheduler)
    for i, mats in enumerate([(15, 16), (16, 17), (18, 19)]):
        assert d.submit(request(d, mats=mats, row=10*i), i)
    d.advance(2)
    assert [r["phase"] for r in d.scheduling()["pending"]] == [2, -1, 2]
    assert times(d, 1) == [] and times(d, 2) == [2]
    d.advance(62)
    assert times(d, 1) == [62]


@pytest.mark.parametrize("name,cycles,total,bits", [
    ("LC-MOV", [0, 16, 39, 55, 94, 114], 130, 8),
    ("GB-MOV", [0, 1, 39, 41, 59], 75, 4),
])
@pytest.mark.parametrize("blocked", [False, True])
def test_public_movement_recovery_locations_and_accounting(name, cycles, total, bits, blocked):
    d = system()
    if blocked:
        assert d.submit(request(d, mats=(6, 16)), 0)
    req = request(d, name)
    locations = req.snapshot()["locations"]
    assert req.size_bytes == -1 and d.submit(req, 1)
    start = 62 if blocked else 1
    d.advance(start+total-1)
    key = name.lower().replace("-", "")
    stats = d.stats()
    assert stats[f"total_num_pud_{key}_requests"] == 1
    assert stats["controller"][f"num_pud_{key}_reqs"] == 1
    assert stats["controller"][f"num_pud_{key}_reqs_completed"] == 0
    assert stats["controller"][f"pud_{key}_moved_bits"] == 0
    d.advance(start+total)
    assert times(d, 1) == [start+t for t in cycles]
    assert all(e["locations"] == locations for e in events(d, 1))
    assert all(e["allocated"] for e in events(d, 1)[1:])
    stats = d.stats()["controller"]
    assert stats[f"num_pud_{key}_reqs_completed"] == 1
    assert stats[f"pud_{key}_moved_bits"] == bits
    assert stats[f"pud_{key}_latency"] == start+total
    assert stats["total_throughput_MBps"] == 0
    d.advance(start+total+30)
    assert d.stats()["controller"][f"num_pud_{key}_reqs_completed"] == 1


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_public_shared_issue_wait_is_separate_from_local_anchor(scheduler):
    d = system(scheduler)
    for i in range(6):
        assert d.submit(request(d, mats=(i, i)), i)
    d.advance(130)
    # A's terminal PRE competes with F's second ACT at CK46. Active oldest
    # wins; F's local ACT->PRE interval remains 5 CK after the delayed ACT.
    assert times(d, 0) == [1, 41, 46]
    assert times(d, 5) == [6, 51, 56]
    done = next(e for e in d.completions() if e["source_id"] == 5)
    assert done["depart"] - times(d, 5)[0] > 61
    assert done["depart"] - times(d, 5)[-1] == 16
    assert len({e["clk"] for e in d.issued()}) == len(d.issued())


def test_public_backpressure_counts_once_and_callback_dependency_join():
    d = system(pending=2)
    dependent = request(d, "NOT", (15, 20), row=11)
    producers = []
    def complete(event):
        producers.append(event)
        if len(producers) == 2:
            assert event["held"] == 0
            assert d.submit(dependent, 2)
    assert d.submit(request(d), 0, complete)
    assert d.submit(request(d, "NOT_COPY", (17, 20)), 1, complete)
    retry = request(d, "MAJ3", (30, 31))
    assert not d.submit(retry, 3)
    assert d.stats()["total_num_pud_maj3_requests"] == 0
    d.advance(106)
    assert len(producers) == 2
    assert d.submit(retry, 3)
    d.advance(300)
    assert len(d.completions()) == 4
    assert times(d, 2)[0] >= max(p["depart"] for p in producers)
    stats = d.stats()
    assert stats["total_num_pud_maj3_requests"] == 1
    assert stats["controller"]["num_pud_maj3_reqs_completed"] == 1
    assert stats["controller"]["pud_maj3_latency"] == next(
        e["depart"]-e["arrive"] for e in d.completions() if e["source_id"] == 3)


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_public_allbank_refresh_mixed_traffic_drains(scheduler):
    d = system(scheduler, refresh=True, nREFI=256, nRFC=32)
    r = resolver()
    for i in range(24):
        name = ["RowCopy", "NOT_COPY", "LC-MOV", "GB-MOV"][i % 4]
        assert d.submit(request(d, name, (2*i, 2*i+1), bank=i % 2), i)
    for i in range(8):
        address = r.inverse([0, 0, 0, 2+i%2, 0, i, 0, 0, 0])[0]
        assert d.submit_ordinary(address, i % 2, 24+i)
    d.advance(6000)
    assert len(d.completions()) == 32
    assert d.scheduling()["held"] == 0 and d.pending == 0
    assert d.scheduling()["recovering"] == [] and d.scheduling()["active_size"] == 0
    assert sum(e["command"] == "REFab" for e in d.issued()) > 10
    assert all(e["allocated"] for e in d.issued() if e["command"].startswith("ACT_PUD"))
    assert len({e["clk"] for e in d.issued()}) == len(d.issued())


@pytest.mark.parametrize("change", ["profile", "dram", "mapper", "channel", "hffs", "ranks", "aqua", "rrs"])
def test_configured_v2_rejects_incompatible_setup(change):
    cfg = controller()
    cfg["pud_placement_profile"] = PROFILE
    channel = "CacheLineInterleave"
    if change == "profile": cfg["pud_placement_profile"] = "unknown"
    if change == "dram": cfg["dram"] = ramulator.dram.DDR4_PuD(org_preset="DDR4_8Gb_x8", timing_preset="DDR4_2400R").to_config()
    if change == "mapper": cfg["addr_mapper"]["impl"] = "PassThroughAddrMapper"
    if change == "channel": channel = "PassThroughChannelMapper"
    if change == "hffs": cfg["dram"]["hffs_per_mat"] = 7
    if change == "ranks": cfg["dram"] = dram_config(ranks=2)
    if change in ("aqua", "rrs"):
        params = (dict(num_art_entries=16, num_fpt_entries=16, num_qrows_per_bank=16, art_threshold=4)
                  if change == "aqua" else dict(num_hrt_entries=16, num_rit_entries=16, rss_threshold=4))
        cfg["controller_plugins"] = [getattr(ramulator.controller_plugin, change.upper())(**params).to_config()]
    with pytest.raises((RuntimeError, ValueError)):
        _LocatedSystemUnderTest(cfg, resolver(), channel, install=False)


def test_public_profile_rejects_legacy_operands_and_preserves_forwarding():
    d = system()
    before = d.stats()
    with pytest.raises(RuntimeError, match="resolved locations"):
        d.send(_bare_request(REQUEST_TYPE_IDS["RowCopy"], [[0]*6]*2, 64))
    assert d.stats() == before and d.pending == 0
    result = d.forwarding()
    assert result["callbacks"] == 3 and not result["retained"]
    assert result["stats"]["controller"]["num_read_reqs_forwarded"] == 1
    assert result["stats"]["controller"]["num_write_reqs_coalesced"] == 1


def test_removed_engine_parameter_is_rejected_by_generated_python_schema():
    assert "pud_compute_engines" not in ramulator.controller.GenericDDR().to_config()
    with pytest.raises(ValueError, match="unknown parameters.*pud_compute_engines"):
        ramulator.controller.GenericDDR(pud_compute_engines=8)
