"""Target-specific arithmetic graphs, synchronized packing, and fusion boundaries."""
import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest
from .generator import PROFILES, generate, write_gemv, placement_profile, _group_placement, trace_header
from .validation import execute_trace, scalar_graph, read_gemv
from .test_integration import inputs


@pytest.mark.parametrize("target", ["DDR4-packed", "GDDR7", "HBM3"])
@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("n", [80, 128, 192, 240, 256, 512])
def test_packed_graph_isolation(target, profile, n):
    p = 512//n
    # Full slices plus a partially filled neighboring mat, distinct input values.
    m = p+1
    layout, trace = generate(profile, m, n, target=target)
    a, x = inputs(profile, m, n)
    expected = scalar_graph(profile, a, x, target=target)
    for poison in (0xA5, 0x5A):
        assert execute_trace(layout, trace, a, x, poison) == expected
    assert len(layout["packed_output_groups"]) == 1
    assert layout["request_counts"] == Counter(line.split()[0] for line in trace)
    assert layout["occupied_mat_rows"] == 2*layout["rows_per_output_per_mat"]
    assert layout["residual_values_per_output"] == placement_profile(target)["hffs_per_mat"]
    assert [r["position_origin"] for r in layout["outputs"]] == [i*n for i in range(p)]+[0]
    assert len({r["domains"][0]["completion_index"] for r in layout["outputs"]}) == 1
    assert not any(line.startswith("GB-MOV") for line in trace)
    depth = len(layout["bank_levels"])
    lc = [list(map(int, line.split()[1:])) for line in trace if line.startswith("LC-MOV")]
    assert any(row[depth:depth+2] == [0, 1] for row in lc)
    if p > 1:
        assert any(row[depth:depth+2] == [0, 0] for row in lc)


@pytest.mark.parametrize("target", ["GDDR7", "HBM3"])
@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("n", [528, 1024])
def test_multimat_graph_and_fusion(target, profile, n):
    layout, trace = generate(profile, 2, n, target=target)
    a, x = inputs(profile, 2, n)
    assert execute_trace(layout, trace, a, x) == scalar_graph(profile, a, x, target=target)
    depth = len(layout["bank_levels"])
    assert list(map(int, trace[0].split()[depth+1:depth+3])) == [0, 3]
    gb = [list(map(int, line.split()[1:]))[depth:depth+2] for line in trace if line.startswith("GB-MOV")]
    assert set(map(tuple, gb)) == {(0, 1), (2, 3)}
    assert layout["outputs"][1]["domains"][0]["mat_begin"] == 2
    if n == 528:
        # A partial tail never becomes storage for another output.
        assert layout["outputs"][1]["position_origin"] == 0


@pytest.mark.parametrize("target", ["GDDR7", "HBM3"])
@pytest.mark.parametrize("profile", PROFILES)
def test_sequential_domains_snapshot_before_reuse(target, profile):
    geometry = placement_profile(target)
    n = 512*geometry["mats_per_chip"]+geometry["hffs_per_mat"]
    layout, trace = generate(profile, 1, n, target=target)
    a, x = inputs(profile, 1, n)
    assert execute_trace(layout, trace, a, x) == scalar_graph(profile, a, x, target=target)
    domains = layout["outputs"][0]["domains"]
    assert len(domains) == 2 and domains[0]["completion_index"] < domains[1]["completion_index"]
    assert layout["residual_values_per_output"] == 2*geometry["hffs_per_mat"]


@pytest.mark.parametrize("target,count,width", [("DDR4-packed", 32, 16), ("GDDR7", 16, 32), ("HBM3", 32, 16)])
def test_characterization_structure_and_counts(target, count, width):
    layout, trace = generate("MIMDRAM-InterMatFirst-int8", 2048, 128, target=target)
    assert layout["packing_factor"] == 4
    assert layout["fused_range_widths"] == [width]*count
    assert len(layout["packed_output_groups"]) == count
    channels = layout["bank_sizes"][0]
    assert [g["context"][0] for g in layout["packed_output_groups"]] == [i%channels for i in range(count)]
    assert layout["occupied_mat_rows"] == 512*60
    assert layout["useful_position_utilization"] == 1
    compute, lc = {"DDR4-packed": (842, 31744), "GDDR7": (796, 7680), "HBM3": (750, 7168)}[target]
    assert layout["request_counts"]["LC-MOV"] == lc
    assert len(trace)-lc == count*compute
    depth = len(layout["bank_levels"])
    for line in trace:
        first, last = map(int, line.split()[depth+1:depth+3])
        assert first//width == last//width


@pytest.mark.parametrize("target", ["GDDR7", "HBM3"])
def test_fusion_before_striping_and_hierarchy_capacity(target):
    geometry = placement_profile(target)
    width = geometry["mats_per_chip"]
    layout, _ = generate("MIMDRAM-InterMatFirst-int8", width*4+1, 128, target=target)
    assert layout["fused_range_widths"] == [width, 1]
    assert [g["context"][0] for g in layout["packed_output_groups"]] == [0, 1]
    channels = geometry["bank_sizes"][0]
    if target == "HBM3":
        for index, context in [(16,[0,1,0,0,0]), (32,[0,0,0,1,0]), (128,[0,0,0,0,1]), (512,[0,0,1,0,0])]:
            assert _group_placement(geometry,60,index)[0] == context
    else:
        assert _group_placement(geometry,60,4)[0] == [0,1]
    import math
    capacity = math.prod(geometry["bank_sizes"])*geometry["chips"]*(geometry["rows_per_bank"]//geometry["rows_per_subarray"])*(geometry["rows_per_subarray"]//60)
    _group_placement(geometry,60,capacity-1)
    with pytest.raises(ValueError, match="capacity"):
        _group_placement(geometry,60,capacity)
    with patch("tools.pud_gemv_generator.generator.lower_to_physical") as lower:
        with pytest.raises(ValueError, match="capacity"):
            generate("MIMDRAM-InterMatFirst-int8",capacity*width*4+1,128,target=target)
        lower.assert_not_called()


@pytest.mark.parametrize("target", ["DDR4", "GDDR7", "HBM3", "DDR4-packed"])
def test_trace_layout_roundtrip(target, tmp_path):
    layout, path = write_gemv("MIMDRAM-InterMatFirst-int8", 3, 128, tmp_path, target=target)
    recovered, trace = read_gemv(path)
    assert recovered == layout
    assert generate(layout["macro_profile"],3,128,target=target) == (recovered,trace)
    if target != "DDR4":
        bad = dict(layout, bank_sizes=[1]*len(layout["bank_sizes"]))
        path.with_suffix(".layout.json").write_text(json.dumps(bad))
        with pytest.raises(ValueError, match="bank_sizes"):
            read_gemv(path)


def test_frozen_ddr4_generation_in_memory():
    root = Path("build/pud-no-engine")
    if not root.exists():
        pytest.skip("local frozen evidence unavailable")
    layouts = sorted(root.glob("MIMDRAM-*/*.layout.json"))
    assert len(layouts) == 14
    for path in layouts:
        frozen = json.loads(path.read_text())
        layout, trace = generate(frozen["macro_profile"],frozen["M"],frozen["N"])
        assert json.dumps(layout,indent=2)+"\n" == path.read_text()
        text, start = trace_header(layout), 0
        for record in layout["outputs"]:
            end = record["domains"][-1]["completion_index"]
            text += f"CHAIN {record['chain_id']}\n"+"\n".join(trace[start:end])+"\n"
            start = end
        assert text == path.with_suffix("").with_suffix(".trace").read_text()


@pytest.mark.parametrize("mutation",["chain", "member", "origin", "residual", "checkpoint"])
def test_layout_rejects_invalid_physical_ownership(mutation):
    from .validation import layout_geometry
    layout, _ = generate("MIMDRAM-InterMatFirst-int8",2,128,target="GDDR7")
    record = layout["outputs"][0]
    if mutation == "chain": record["chain_id"] = -1
    if mutation == "member": layout["packed_output_groups"][0]["output_ids"] = [0,0]
    if mutation == "origin": record["position_origin"] = 1
    if mutation == "residual": record["domains"][0]["residual_positions"][0] = 128
    if mutation == "checkpoint": record["domains"][0]["checkpoint_request"] += 1
    with pytest.raises(ValueError): layout_geometry(layout)
