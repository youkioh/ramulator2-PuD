"""W2 paired submission/consumer contract and public ingress guards."""

import gc

import pytest
import ramulator
from ramulator._ramulator_test import (
    _LocatedSystemUnderTest, _PuDRoutingSystemUnderTest, _bare_request,
    _located_request, _located_lifetime, _tamper_location, _validate_located_request,
)
from ramulator.dram.spec import REQUEST_TYPE_IDS
from tests.unit_tests.test_pud_location import resolver, dram_config


COMPUTE = dict(RowCopy=2, MAJ3=3, MAJ5=5, NOT=1, NOT_COPY=2)
ALL = COMPUTE | {"LC-MOV": 2, "GB-MOV": 2}


def descriptor(row=0, mats=(0, 0), group=None, **kwargs):
    return dict(kind="compute" if group is None else "group",
                row=[0, 0, 0, 0, row], range=list(mats),
                **({} if group is None else {"group": group}), **kwargs)


def request(r, name, desc=None, size=None):
    movement = name in ("LC-MOV", "GB-MOV")
    if desc is None:
        desc = [descriptor(i, (i, i) if name == "GB-MOV" else (0, 0),
                           i if movement else None) for i in range(ALL[name])]
    return _located_request(r, REQUEST_TYPE_IDS[name], desc,
                            (-1 if movement else 64) if size is None else size)


def validate(r, req, config=None, **kwargs):
    return _validate_located_request(r, req, config or dram_config(), **kwargs)


def controller(config=None, mapper="RoBaRaCoCh"):
    return dict(impl="GenericDDR", dram=config or dram_config(),
                scheduler=dict(impl="FRFCFS"), refresh_manager=dict(impl="NoRefresh"),
                row_policy=dict(impl="Open"), addr_mapper=dict(impl=mapper))


def synthetic():
    # W1's coordinated software fixture, including non-adjacent GB wiring.
    successors = [m + 1 if m % 8 != 7 else -1 for m in range(64)]
    successors[0] = 2
    profile = dict(name="synthetic coherent test profile", mats_per_chip=8,
                   cells_per_mat_row=1024, hffs_per_mat=8, gb_successor=successors,
                   burst_to_group=[(17*b + 3) % 128 for b in range(128)],
                   bit_to_slot=[(b + 8) % 512 for b in range(512)],
                   group_position_to_column=[8*g + 7-h for g in range(128) for h in range(8)])
    config = dram_config(hffs_per_mat=8)
    return resolver(config=config, profile=profile), config


@pytest.mark.parametrize("name", COMPUTE)
@pytest.mark.parametrize("mats", [(0, 0), (127, 127), (0, 127), (15, 16)])
def test_all_compute_ranges_and_columns_do_not_narrow_rows(name, mats):
    r = resolver()
    desc = [descriptor(i, mats, column=i) for i in range(COMPUTE[name])]
    req = request(r, name, desc, size=1)
    assert validate(r, req) == dict(route=0)
    small = req.snapshot()
    req.size_bytes = 64
    assert validate(r, req) == dict(route=0)
    assert small["locations"] == req.snapshot()["locations"]
    assert all(o["cell_count"] == (mats[1]-mats[0]+1)*512 for o in small["locations"])
    assert all(o["range"] == list(mats) and o["group"] is None for o in small["locations"])


@pytest.mark.parametrize("replacement", [False, True])
def test_column_absence_is_only_a_legacy_projection_sentinel(replacement):
    r, config = synthetic() if replacement else (resolver(), dram_config())
    unspecified = request(r, "NOT", [descriptor(4, (0, 0))])
    supplied = request(r, "NOT", [descriptor(4, (0, 0), column=127)])
    group = 3 if replacement else 0
    movement = request(r, "LC-MOV", [descriptor(4, (0, 0), group)]*2)
    for req in [unspecified, supplied, movement]:
        validate(r, req, config)
    absent = unspecified.snapshot(cells=True)
    explicit = supplied.snapshot(cells=True)
    assert absent["external"][0][-1] == -1
    assert explicit["external"][0][-1] == 127
    assert absent["locations"] == explicit["locations"]
    assert absent["locations"][0]["burst"] is None
    assert absent["locations"][0]["group"] is None
    assert absent["locations"][0]["cell_count"] == (1024 if replacement else 512)
    selected = movement.snapshot()
    assert all(o["group"] == group and o["burst"] == 0 for o in selected["locations"])
    assert all(v[-1] == 0 for v in selected["external"])


@pytest.mark.parametrize("column", [-1, -2, 128])
@pytest.mark.parametrize("group", [None, 0])
def test_explicit_invalid_column_is_not_absence(column, group):
    r = resolver()
    with pytest.raises(ValueError, match="BurstColumn out of bounds"):
        request(r, "NOT" if group is None else "LC-MOV",
                [descriptor(group=group, column=column)] * (1 if group is None else 2))


@pytest.mark.parametrize("name", ALL)
@pytest.mark.parametrize("count", [0, 1, 2, 3, 4, 5, 6])
def test_operand_counts(name, count):
    r = resolver()
    movement = name in ("LC-MOV", "GB-MOV")
    req = request(r, name, [descriptor(i, (i, i) if name == "GB-MOV" else (0, 0),
                                      0 if movement else None) for i in range(count)])
    if (name == "RowCopy" and count >= 2) or count == ALL[name]:
        validate(r, req)
    else:
        with pytest.raises(RuntimeError, match="invalid operand count"):
            validate(r, req)


def test_arbitrary_rowcopy_destination_list():
    r = resolver()
    req = request(r, "RowCopy", [descriptor(i, (15, 16)) for i in range(512)])
    validate(r, req)
    assert len(req.snapshot()["locations"]) == 512
    lifetime = _located_lifetime(req, dram_config())
    assert len(lifetime["occurrences"]) == 513


@pytest.mark.parametrize("mats", [[], [0], [0, 2, 4], [-1, 0], [0, 128], [3, 2]])
@pytest.mark.parametrize("name", ["NOT", "LC-MOV", "GB-MOV"])
def test_invalid_ranges(name, mats):
    r = resolver()
    d = descriptor(group=0 if name != "NOT" else None)
    d["range"] = mats
    with pytest.raises(ValueError):
        request(r, name, [d])


@pytest.mark.parametrize("change", ["missing_range", "bit", "per_mat_groups", "regions"])
def test_unsupported_origin_or_scope_forms(change):
    r = resolver()
    d = descriptor(group=0)
    if change == "missing_range": del d["range"]
    elif change == "bit": d["kind"] = "bit"
    else: d[change] = [0, 1]
    with pytest.raises(ValueError):
        request(r, "LC-MOV", [d, d])


@pytest.mark.parametrize("name", ["RowCopy", "MAJ3", "MAJ5", "NOT_COPY", "LC-MOV"])
def test_operand_ranges_must_match(name):
    r = resolver()
    desc = [descriptor(i, (0, i), 0 if name == "LC-MOV" else None) for i in range(ALL[name])]
    with pytest.raises(RuntimeError, match="same mat range"):
        validate(r, request(r, name, desc))


@pytest.mark.parametrize("name", ["MAJ3", "MAJ5"])
def test_majority_repeated_physical_row_despite_different_column(name):
    r = resolver()
    desc = [descriptor(4, (15, 16), column=i) for i in range(ALL[name])]
    with pytest.raises(RuntimeError, match="distinct physical rows"):
        validate(r, request(r, name, desc))


@pytest.mark.parametrize("index,value", [(1, 1), (2, 1), (3, 1), (4, 1024)])
@pytest.mark.parametrize("name", ["RowCopy", "LC-MOV", "GB-MOV"])
def test_common_bank_subarray_context(index, value, name):
    config = dram_config(4)
    r = resolver(4)
    desc = [descriptor(0, (i, i) if name == "GB-MOV" else (0, 0),
                       0 if name != "RowCopy" else None) for i in range(2)]
    desc[1]["row"][index] = value
    req = request(r, name, desc)
    # Shape/channel routing is separate from controller placement.
    assert validate(r, req, config, placement=False)["route"] == 0
    with pytest.raises(RuntimeError, match="Bank and subarray context"):
        validate(r, req, config)


@pytest.mark.parametrize("field", ["association", "missing_origin", "external_row", "burst",
                                    "cell_count", "range", "missing_resolver", "count", "legacy_metadata"])
def test_incoherent_pairs_rejected(field):
    r = resolver()
    req = _tamper_location(request(r, "LC-MOV"), field)
    with pytest.raises((ValueError, RuntimeError)):
        validate(r, req)


def test_changed_external_views_and_foreign_expected_association():
    r = resolver()
    for level in range(6):
        req = request(r, "RowCopy")
        external = req.operands
        external[0][level] += 1
        req.operands = external
        with pytest.raises(RuntimeError, match="external projection"):
            validate(r, req)
    req = request(r, "RowCopy")
    req.operands = [req.operands[0][:-1], req.operands[1]]
    with pytest.raises(RuntimeError): validate(r, req)
    for foreign in [resolver(), resolver(context=dict(address_space="other"))]:
        with pytest.raises(RuntimeError, match="profile/routing association"):
            validate(foreign, request(r, "RowCopy"))
    with pytest.raises(RuntimeError, match="controller channel"):
        validate(r, request(r, "RowCopy"), channel=1)
    with pytest.raises(ValueError, match="rank context mismatch"):
        validate(r, request(r, "RowCopy"), dram_config(4))


@pytest.mark.parametrize("name", ALL)
def test_bare_legacy_vectors_do_not_become_v2(name):
    r = resolver()
    good = request(r, name)
    bare = _bare_request(good.type_id, good.operands, good.size_bytes)
    with pytest.raises(RuntimeError): validate(r, bare)


@pytest.mark.parametrize("name", ALL)
def test_wrong_compute_group_or_movement_whole_row(name):
    r = resolver()
    desc = [descriptor(i, (i, i) if name == "GB-MOV" else (0, 0),
                       0 if name in COMPUTE else None) for i in range(ALL[name])]
    with pytest.raises(RuntimeError, match="whole compute mat-rows or explicit movement groups"):
        validate(r, request(r, name, desc))


@pytest.mark.parametrize("mats,bits", [((0, 0), 4), ((15, 16), 8), ((0, 127), 512)])
def test_lc_exact_bits_and_ordered_different_groups(mats, bits):
    r = resolver()
    req = request(r, "LC-MOV", [descriptor(1024, mats, 0), descriptor(2047, mats, 127)])
    assert validate(r, req)["bits"] == bits
    for loc in req.snapshot(cells=True)["locations"]:
        for i, cell in enumerate(loc["cells"]):
            assert r.resolve(*r.inverse(cell))["hff"] == i % 4


@pytest.mark.parametrize("source,dest", [(1, 0), (15, 16), (127, 0), (0, 2), (0, 0)])
def test_gb_illegal_topology(source, dest):
    r = resolver()
    with pytest.raises(RuntimeError, match="directed singleton neighbors"):
        validate(r, request(r, "GB-MOV", [descriptor(0, (source, source), 0), descriptor(1, (dest, dest), 127)]))


def test_gb_wider_endpoints_and_group_projection():
    r = resolver()
    with pytest.raises(RuntimeError, match="singleton"):
        validate(r, request(r, "GB-MOV", [descriptor(0, (0, 1), 0), descriptor(1, (2, 2), 1)]))
    for group in [-1, 128, 1023]:
        with pytest.raises(ValueError): request(r, "LC-MOV", [descriptor(group=group)]*2)
    with pytest.raises(ValueError, match="group/burst projection"):
        request(r, "LC-MOV", [descriptor(group=0, column=1)]*2)


@pytest.mark.parametrize("name", ["LC-MOV", "GB-MOV"])
@pytest.mark.parametrize("size", [0, 1, 64])
def test_movement_rejects_supplied_sizes(name, size):
    r = resolver()
    with pytest.raises(RuntimeError, match="size_bytes"):
        validate(r, request(r, name, size=size))


@pytest.mark.parametrize("name", ALL)
def test_copy_retry_occurrence_and_completion_lifetime(name):
    r = resolver()
    req = request(r, name)
    before = req.snapshot()
    copied = req.copy()
    del r, req
    gc.collect()
    assert copied.snapshot() == before
    result = _located_lifetime(copied, dram_config())
    assert all(result[k] for k in ("failed_enqueue", "retry", "prerequisite_unchanged", "same_bundle", "descriptor_survives"))
    assert result["completion"]["locations"] == before["locations"]
    assert result["completion"]["history"] == list(range(1, len(result["occurrences"])+1))
    assert result["completion"]["cursor"] == len(result["occurrences"])
    for occurrence in result["occurrences"]:
        i = occurrence["operand"]
        assert occurrence["external"] == before["external"][i]
        assert occurrence["range"] == before["locations"][i]["range"]


@pytest.mark.parametrize("name", ALL)
def test_real_memory_system_routing_retry_and_acceptance(name):
    r = resolver()
    req = request(r, name)
    req.addr_vec = [99, 99, 99, 99, 99, 99]  # Not the routing authority.
    system = _PuDRoutingSystemUnderTest(1)
    result = system.retry_located(req)
    assert not result["first"] and result["second"] and result["same_bundle"]
    assert result["receiver"] == 0 and result["external"] == req.operands
    key = f"total_num_pud_{name.lower().replace('-mov', 'mov')}_requests"
    assert result["before_retry"][key] == 0
    assert system.stats()[key] == 1


@pytest.mark.parametrize("name", ALL)
@pytest.mark.parametrize("path", ["system", "controller", "priority", "issue"])
@pytest.mark.parametrize("install", [False, True])
def test_v2_requires_profile_and_cannot_bypass_normal_ingress(name, path, install):
    r = resolver()
    system = _LocatedSystemUnderTest(controller(), r, install=install)
    before = system.stats()
    if install and path in ("system", "controller"):
        assert system.send(request(r, name), path)
        assert system.pending == 1
    else:
        with pytest.raises(RuntimeError, match="execution is unavailable"):
            system.send(request(r, name), path)
        assert system.pending == 0 and system.stats() == before


def test_invalid_ingress_acquires_nothing_and_changes_no_acceptance():
    r = resolver()
    system = _LocatedSystemUnderTest(controller(), r)
    before = system.stats()
    invalid = request(r, "RowCopy")
    invalid.operands = [[0]*6]*2
    for req in [invalid, _bare_request(2, [[0]*6]*2, 64), request(resolver(), "RowCopy")]:
        with pytest.raises((RuntimeError, ValueError)): system.send(req)
        assert system.pending == 0 and system.stats() == before
    bare = _bare_request(2, [[0]*6]*2, 64)
    for path in ["priority", "issue"]:
        with pytest.raises(RuntimeError, match="execution is unavailable"):
            system.send(bare, path)
        assert system.pending == 0 and system.stats() == before


@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize("type_id", [0, 1])
def test_actual_ordinary_and_pud_consumers_share_cells_and_order(replacement, type_id):
    r, config = synthetic() if replacement else (resolver(), dram_config())
    system = _LocatedSystemUnderTest(controller(config), r)
    for address in [0, 1, 7, 8, 63, 64, 8191, 8192, 131072, 131072*1024-1, 131072*1024]:
        ordinary = system.ordinary(address, type_id)
        assert ordinary["accepted"] and not ordinary["retained"] and not ordinary["completion_retained"]
        assert ordinary["origin"] == [address, 0] and ordinary["requested_size_bytes"] == 1
        assert ordinary["activation_count"] == 65536 and ordinary["burst_count"] == 512
        burst = set(map(tuple, ordinary["burst"]))
        act = set(map(tuple, ordinary["activation"]))
        # Derive endpoint selection through W1 segments/cells, never through
        # consumer copies of chip/mat/group decode formulas.
        for bit in [0, 3, 4, 7]:
            resolved = r.resolve(address, bit)
            assert tuple(resolved["cell"]) in burst <= act
        row = ordinary["external"][:5]
        width = r.info["hffs"]
        first, last = (7, 8) if replacement else (15, 16)
        compute = request(r, "NOT", [dict(kind="compute", row=row, range=[first, last])])
        lc = request(r, "LC-MOV", [dict(kind="group", row=row, range=[first, last], group=ordinary["group"])]*2)
        for req in [compute, lc]: validate(r, req, config)
        compute_cells = set(map(tuple, compute.snapshot(cells=True)["locations"][0]["cells"]))
        lc_cells = lc.snapshot(cells=True)["locations"][0]["cells"]
        assert compute_cells <= act
        assert set(map(tuple, lc_cells)) == burst & compute_cells
        for i, cell in enumerate(lc_cells): assert r.resolve(*r.inverse(cell))["hff"] == i % width
        dest = 2 if replacement else 1
        gb = request(r, "GB-MOV", [dict(kind="group", row=row, range=[m, m], group=ordinary["group"]) for m in [0, dest]])
        assert validate(r, gb, config)["bits"] == width
        for endpoint in gb.snapshot(cells=True)["locations"]:
            assert set(map(tuple, endpoint["cells"])) <= burst
            assert [r.resolve(*r.inverse(c))["hff"] for c in endpoint["cells"]] == list(range(width))
    # Requested byte count annotates the ordinary burst; it is not a write mask.
    one = system.ordinary(0, type_id, size=1)
    full = system.ordinary(0, type_id, size=64)
    assert one["burst"] == full["burst"] and one["activation"] == full["activation"]


def test_synthetic_topology_and_bounds_are_profile_owned():
    r, config = synthetic()
    good = request(r, "GB-MOV", [descriptor(0, (0, 0), 3), descriptor(1, (2, 2), 20)])
    assert validate(r, good, config)["bits"] == 8
    assert good.operands[0][-1] == 0 and good.operands[1][-1] == 1
    for a, b in [(0, 1), (7, 8), (2, 0)]:
        with pytest.raises(RuntimeError, match="neighbors"):
            validate(r, request(r, "GB-MOV", [descriptor(0, (a, a), 3), descriptor(1, (b, b), 20)]), config)
    with pytest.raises(ValueError): request(r, "NOT", [descriptor(0, (0, 64))])
    lc = request(r, "LC-MOV", [descriptor(0, (7, 8), 3)]*2)
    assert validate(r, lc, config)["bits"] == 16


@pytest.mark.parametrize("dram_class", [ramulator.dram.DDR4, ramulator.dram.DDR4_PuD, ramulator.dram.DDR4_PuD_Movement])
@pytest.mark.parametrize("ranks", [1, 4])
def test_ordinary_profile_consistency_across_standards_and_ranks(dram_class, ranks):
    config = dram_config(ranks, dram_class=dram_class)
    r = resolver(config=config)
    system = _LocatedSystemUnderTest(controller(config), r)
    for address in [7, 8192, 8192*ranks, 32768*ranks, 131072*ranks*1024, r.info["capacity_bytes"]-1]:
        actual = system.ordinary(address, 0, cells=False)
        assert actual["external"] == r.resolve(address, 0)["external"]
        assert actual["cell"] == r.resolve(address, 0)["cell"]


def test_ordinary_mapping_mismatch_and_out_of_domain_rejected_before_acceptance():
    r = resolver()
    system = _LocatedSystemUnderTest(controller(), r)
    before = system.stats()
    with pytest.raises(RuntimeError, match="mapper result"):
        system.ordinary(0, 0, wrong_intra=131072)
    for address in [-1, r.info["capacity_bytes"]]:
        with pytest.raises(ValueError): system.ordinary(address, 0)
    assert system.stats() == before


def test_actual_mapper_configuration_must_match_resolver():
    r = resolver()
    with pytest.raises(RuntimeError, match="controller mapper"):
        _LocatedSystemUnderTest(controller(mapper="PassThroughAddrMapper"), r)
    system = _LocatedSystemUnderTest(controller(), r, channel_mapper="PassThroughChannelMapper")
    before = system.stats()
    with pytest.raises(RuntimeError, match="routing disagrees"):
        system.ordinary(0, 0)
    assert system.stats() == before


def test_profile_mapping_preserves_ordinary_forwarding_and_coalescing():
    r = resolver()
    result = _LocatedSystemUnderTest(controller(), r).forwarding()
    assert result["callbacks"] == 3 and not result["retained"]
    stats = result["stats"]["controller"]
    assert stats["num_write_reqs"] == 2 and stats["num_write_reqs_coalesced"] == 1
    assert stats["num_read_reqs"] == 1 and stats["num_read_reqs_forwarded"] == 1
