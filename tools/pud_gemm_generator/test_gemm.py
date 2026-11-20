"""Full placement coverage, small physical execution, and artifact ownership."""
from collections import Counter
from copy import deepcopy
import json

import pytest
from tools.pud_gemv_generator import validation as gemv_validation
from .generator import PROFILES, generate, _generate, _write_artifacts
from .validation import validate_layout, validate_trace, read_gemm, _replay, _scalar_output


@pytest.mark.parametrize("profile", PROFILES)
def test_target_coverage(profile):
    layout, trace = generate(profile)
    validate_trace(layout, trace)
    assert len(layout["chains"]) == 16
    assert len(layout["outputs"]) == 8*2048
    coverage, locations = set(), set()
    for record in layout["outputs"]:
        h, j = record["query"], record["key"]
        assert (h, j) not in coverage
        coverage.add((h, j))
        domain = record["domains"][0]
        location = (*record["context"], record["band"], domain["mat_begin"], record["position_origin"])
        assert location not in locations
        locations.add(location)
        assert record["chip"] == h == domain["mat_begin"]//16
        assert j == 128*record["chain_id"]+64*record["band"]+4*(domain["mat_begin"]%16)+record["position_origin"]//128
    assert coverage == {(h, j) for h in range(8) for j in range(2048)}
    assert Counter((r["chip"], r["chain_id"]) for r in layout["outputs"]) == {
        (h, b): 128 for h in range(8) for b in range(16)}
    assert all(list(map(int, line.split()[5:7])) == [0, 127] for line in trace)
    assert layout["logical_scalar_mul_calls"] == 8*2048*128
    assert layout["logical_pud_scalar_add_calls"] == 8*2048*124


def inputs(profile):
    if profile.endswith("int8"):
        q = [[(r*r+3*h*r+h+1) & 255 for r in range(128)] for h in range(8)]
        k = [[(r*r+3*j*r+j+7) & 255 for j in range(2048)] for r in range(128)]
    else:
        base = 0x28 if profile.endswith("e4m3") else 0x34
        q = [[(base+(r+h)%3) | (0x80 if (r+h)%5 == 0 else 0) for r in range(128)] for h in range(8)]
        k = [[(base+(r+j)%3) | (0x80 if (r//4+j)%2 else 0) for j in range(2048)] for r in range(128)]
    assert len({tuple(row) for row in q}) == 8
    return q, k


@pytest.mark.parametrize("format_", ["int8", "fp8-e4m3", "fp8-e5m2"])
def test_n128_schedules_have_identical_physical_request_bodies(format_):
    inter, inter_trace = generate("MIMDRAM-InterMatFirst-"+format_)
    intra, intra_trace = generate("MIMDRAM-IntraMatFirst-"+format_)
    # generate returns Request bodies separately from profile-specific headers.
    assert inter_trace == intra_trace
    assert inter["chains"] == intra["chains"]
    assert inter["band_groups"] == intra["band_groups"]


def _replay_with_residuals(monkeypatch, layout, trace, q, k):
    """Observe raw readout operands at the existing untimed host-fold boundary."""
    operations = gemv_validation.scalar_operations
    readout = []

    def observed_operations(profile):
        add, mul = operations(profile)

        def observed_add(a, b):
            readout.append(b)
            return add(a, b)

        return observed_add, mul

    # Physical arithmetic uses execute_physical; these scalar ADD calls only
    # fold four residuals, then fold the domain sum into the output sum.
    with monkeypatch.context() as patch:
        patch.setattr(gemv_validation, "scalar_operations", observed_operations)
        values = _replay(layout, trace, q, k)
    assert len(readout) == 5*len(layout["outputs"])
    residuals = {(r["query"], r["key"]): tuple(readout[5*i:5*i+4])
                 for i, r in enumerate(layout["outputs"])}
    return values, residuals


@pytest.mark.parametrize("format_", ["int8", "fp8-e4m3", "fp8-e5m2"])
def test_complete_packed_bank_fused_equals_chip_local(monkeypatch, format_):
    profile = "MIMDRAM-InterMatFirst-"+format_
    fused, fused_trace = _generate(profile, banks=(5,))
    local, local_trace = _generate(profile, banks=(5,), fused=False)
    for layout, trace in ((fused, fused_trace), (local, local_trace)):
        validate_trace(layout, trace, _partial=True)
        assert len(layout["chains"]) == 1
        assert [len(g["output_ids"]) for g in layout["band_groups"]] == [512, 512]
        assert {(r["query"], r["key"]) for r in layout["outputs"]} == {
            (h, j) for h in range(8) for j in range(640, 768)}
    assert all(line.split()[5:7] == ["0", "127"] for line in fused_trace)
    assert all(int(line.split()[5])//16 == int(line.split()[6])//16 for line in local_trace)
    assert len(local_trace) == 8*len(fused_trace)
    q, k = inputs(profile)
    fused_values, fused_residuals = _replay_with_residuals(monkeypatch, fused, fused_trace, q, k)
    local_values, local_residuals = _replay_with_residuals(monkeypatch, local, local_trace, q, k)
    assert fused_residuals == local_residuals
    assert len(fused_residuals) == 1024
    assert all(len(values) == 4 for values in fused_residuals.values())
    expected = {(r["query"], r["key"]): _scalar_output(profile, q[r["query"]], k, r["key"])
                for r in fused["outputs"]}
    assert fused_values == local_values == expected


@pytest.mark.parametrize("profile", PROFILES)
def test_chip_queries_fusion_poison_and_retained_bands(profile):
    q, k = inputs(profile)
    # Two occupied slices/MAT: remaining positions are poisoned, not padding.
    fused, trace = _generate(profile, banks=(5,), local_outputs=2)
    local, local_trace = _generate(profile, banks=(5,), local_outputs=2, fused=False)
    validate_trace(fused, trace, _partial=True)
    validate_trace(local, local_trace, _partial=True)
    expected = {(r["query"], r["key"]): _scalar_output(profile, q[r["query"]], k, r["key"])
                for r in fused["outputs"]}
    assert len(set(expected.values())) > 1
    assert _replay(fused, trace, q, k) == expected
    assert _replay(fused, trace, q, k, poison=0x5A) == expected
    assert _replay(local, local_trace, q, k) == expected
    # Partial occupied ranges have gaps between chips, so range fusion must not
    # invent storage coverage. A complete chip-local group exercises widening.
    full, full_trace = _generate(profile, banks=(0,), local_outputs=64)
    assert all(line.split()[5:7] == ["0", "127"] for line in full_trace)


@pytest.mark.parametrize("mutation", ["chain", "band", "query", "key", "residual", "checkpoint", "rows", "duplicate"])
def test_invalid_layout(mutation):
    layout, _ = _generate("MIMDRAM-InterMatFirst-int8", banks=(0,), local_outputs=2)
    record = layout["outputs"][0]
    if mutation == "chain": layout["chains"][0]["chain_id"] = 1
    if mutation == "band": layout["band_groups"][0]["band"] = 1
    if mutation == "query": record["query"] = 1
    if mutation == "key": record["key"] += 1
    if mutation == "residual": record["domains"][0]["residual_positions"][0] += 1
    if mutation == "checkpoint": layout["chains"][0]["checkpoint_request"] += 1
    if mutation == "rows": record["input_rows"][0][0] += 1
    if mutation == "duplicate": layout["outputs"][1] = deepcopy(record)
    with pytest.raises(ValueError):
        validate_layout(layout, _partial=True)


@pytest.mark.parametrize("mutation", ["bank", "range", "row_band", "gb", "group"])
def test_illegal_physical_scope(mutation):
    layout, trace = _generate("MIMDRAM-InterMatFirst-int8", banks=(0,), local_outputs=2)
    index = next(i for i, line in enumerate(trace) if line.startswith("LC-MOV"))
    fields = trace[index].split()
    if mutation == "bank": fields[4] = "1"
    if mutation == "range": fields[6] = "128"
    if mutation == "row_band": fields[7] = str(layout["rows_per_band_per_mat"])
    if mutation == "gb": fields[0] = "GB-MOV"
    if mutation == "group": fields[8] = "128"
    trace[index] = " ".join(fields)
    layout["request_counts"] = dict(Counter(line.split()[0] for line in trace))
    with pytest.raises(ValueError):
        validate_trace(layout, trace, _partial=True)


def test_artifact_roundtrip_and_rejection(tmp_path):
    layout, trace = generate("MIMDRAM-InterMatFirst-int8")
    path = _write_artifacts(layout, trace, tmp_path)
    assert path.read_text().splitlines()[0] == "PUD_TRACE 2"
    assert read_gemm(path) == (layout, trace)
    original = path.read_text()
    for bad in (original.replace("CHAIN 1\n", "CHAIN 0\n", 1),
                original.replace("PUD_TRACE 2", "PUD_TRACE", 1), original+"CHAIN 16\n"):
        path.write_text(bad)
        with pytest.raises(ValueError):
            read_gemm(path)
    path.write_text(original)
    layout["outputs"][0]["checkpoint_request"] += 1
    path.with_suffix(".layout.json").write_text(json.dumps(layout))
    with pytest.raises(ValueError):
        read_gemm(path)


def _boundary_fixture(layout, trace, fused):
    """Keep four adjacent chip-boundary pairs from the real full-rank stream.

    All eight query identities remain. This is a physical replay fixture only,
    not an alternate generator policy or a public reduced GEMM shape.
    """
    keep = {15, 16, 47, 48, 79, 80, 111, 112}
    result, ends = [], {0: 0}
    for index, line in enumerate(trace, 1):
        fields = line.split()
        mats = sorted(keep.intersection(range(int(fields[5]), int(fields[6])+1)))
        ranges = []
        for mat in mats:
            if fused and ranges and ranges[-1][1]+1 == mat:
                ranges[-1][1] = mat
            else:
                ranges.append([mat, mat])
        for first, last in ranges:
            result.append(" ".join(fields[:5]+[str(first), str(last)]+fields[7:]))
        ends[index] = len(result)
    layout = deepcopy(layout)
    layout["outputs"] = [r for r in layout["outputs"] if r["domains"][0]["mat_begin"] in keep]
    for chain in layout["chains"]:
        old_start = chain["first_request_index"]-1
        chain["checkpoint_request"] = ends[old_start+chain["checkpoint_request"]]-ends[old_start]
        chain["first_request_index"] = ends[old_start]+1
        chain["completion_index"] = ends[chain["completion_index"]]
    ids = {r["output_id"] for r in layout["outputs"]}
    for group in layout["band_groups"]:
        group["output_ids"] = [i for i in group["output_ids"] if i in ids]
        group["first_request_index"] = ends[group["first_request_index"]-1]+1
        group["completion_index"] = ends[group["completion_index"]]
    for record in layout["outputs"]:
        record["first_request_index"] = ends[record["first_request_index"]-1]+1
        record["completion_index"] = ends[record["completion_index"]]
        record["checkpoint_request"] = record["completion_index"]
        record["domains"][0]["completion_index"] = record["completion_index"]
        record["domains"][0]["checkpoint_request"] = record["checkpoint_request"]
    layout["request_count"] = len(result)
    layout["request_counts"] = dict(Counter(line.split()[0] for line in result))
    validate_trace(layout, result, _partial=True)
    return layout, result


@pytest.mark.parametrize("format_", ["int8", "fp8-e4m3", "fp8-e5m2"])
def test_actual_cross_chip_ranges_equal_chip_local_execution(format_):
    profile = "MIMDRAM-InterMatFirst-"+format_
    layout, trace = _generate(profile, banks=(0,))
    fused, fused_trace = _boundary_fixture(layout, trace, True)
    local, local_trace = _boundary_fixture(layout, trace, False)
    assert len(local_trace) == 2*len(fused_trace)
    assert all(int(line.split()[5])//16 != int(line.split()[6])//16 for line in fused_trace)
    q, k = inputs(profile)
    expected = {(r["query"], r["key"]): _scalar_output(profile, q[r["query"]], k, r["key"])
                for r in fused["outputs"]}
    assert _replay(fused, fused_trace, q, k) == _replay(local, local_trace, q, k) == expected
