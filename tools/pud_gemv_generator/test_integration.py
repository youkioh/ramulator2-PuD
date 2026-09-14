"""Focused composition cases; existing suites own primitive validation."""
from collections import Counter
from unittest.mock import patch
import pytest
from tools.pud_operation_generator.requirements import operation_requirements as micro_operation_requirements
from . import generator
from .validation import execute_trace, scalar_graph

CASES = [(1, 4), (1, 512), (1, 1024), (1, 1536), (1, 516), (2, 12), (2, 516), (2, 1028), (1, 8196)]


def inputs(profile, m, n):
    if profile == "int8-gemv":
        return [[(j*37+i*19+3) & 255 for j in range(n)] for i in range(m)], [(j*11+7) & 255 for j in range(n)]
    base = 0x28 if profile == "fp8-e4m3-gemv" else 0x34
    return [[(base + (j+i) % 3) | (0x80 if (j//4+i) % 2 else 0) for j in range(n)] for i in range(m)], [base + j % 2 for j in range(n)]


@pytest.mark.parametrize("profile", generator.PROFILES)
@pytest.mark.parametrize("m,n", CASES)
def test_physical_composition(profile, m, n):
    requirements = micro_operation_requirements()
    calls = []
    original = generator.lower_to_physical

    def instantiate(program, layout):
        result = original(program, layout)
        calls.append((program, layout, result))
        return result

    with patch.object(generator, "lower_to_physical", instantiate):
        metadata, trace = generator.generate(profile, m, n)
    matrix, vector = inputs(profile, m, n)
    actual = execute_trace(metadata, trace, matrix, vector)
    assert actual == scalar_graph(profile, matrix, vector)
    if profile == "int8-gemv":
        assert actual == [sum(a*x for a, x in zip(row, vector)) & 255 for row in matrix]
    if n in (12, 516, 1028):
        assert execute_trace(metadata, trace, matrix, vector, poison=0x5A) == actual

    names = generator.PROFILES[profile]
    assert set(metadata["micro_operation_requirements"]) == set(names)
    assert metadata["micro_operation_temporary_rows_per_mat"] == max(requirements[name]["additional_temporary_rows"] for name in names)
    assert len(calls) == sum(metadata["micro_operation_counts"].values())
    assert metadata["request_counts"] == dict(Counter(line.split()[0] for line in trace))
    assert len(trace) == metadata["request_count"]
    geometry = generator.placement_profile()
    for program, layout, lowered in calls:
        assert len(layout.temporary_rows) == lowered.additional_temporary_rows
        designated = set(layout.inputs.values()) | set(layout.constants.values()) | set(layout.outputs.values())
        assert not designated.intersection(layout.temporary_rows)
        assert set(row for primitive in lowered.primitives for row in primitive.physical_rows) <= designated | set(layout.temporary_rows)
        assert any(program.trace == generator.BUILDERS[name]().trace for name in names)
    occupied = set()
    for record in metadata["outputs"]:
        ownership = [set(range(first, first+8)) for first in record["macro_operation_temporary_row_bases"].values()]
        ownership += [set(record["micro_operation_temporary_rows"]), set(record["constant_rows"].values())]
        ownership += [set(range(first, first+8)) for pair in record["input_rows"] for first in pair]
        assert sum(map(len, ownership)) == len(set.union(*ownership))
        first = record["domains"][0]["mat_begin"]
        k = max(d["mat_count"] for d in record["domains"])
        cells = {(*record["context"], mat, row)
                 for mat in range(first, first+k) for row in set.union(*ownership)}
        assert occupied.isdisjoint(cells)
        occupied.update(cells)
        terms = []
        start = 0
        for domain in record["domains"]:
            assert domain["mat_begin"] == first
            assert domain["sink_mat"] == first + domain["mat_count"]-1
            for mat in range(domain["mat_count"]):
                terms.extend(start+mat*512+lane for lane in range(min(512, domain["elements"]-mat*512)))
            start += domain["elements"]
        assert terms == list(range(n))
    for line in trace:
        fields = line.split()
        if fields[0] == "GB-MOV":
            assert geometry["gb_successor"][int(fields[5])] == int(fields[6])


@pytest.mark.parametrize("k", [1, 2, 3, 16])
def test_static_placement_boundaries(k):
    g = generator.placement_profile()
    # Actual baseline geometry; exercise high indices without generating huge traces.
    q = 16 // k
    p = 8 * q
    slots = 16 * 64 * p
    footprint = 60
    cases = [
        (0, [0, 0, 0, 0], 0, 0, 0),
        (q-1, [0, 0, 0, 0], 0, 0, (q-1)*k),
        (q, [0, 0, 0, 0], 0, 0, 16),
        (p, [0, 0, 0, 1], 0, 0, 0),
        (4*p, [0, 0, 1, 0], 0, 0, 0),
        (16*p, [0, 0, 0, 0], 1, 0, 0),
        (slots, [0, 0, 0, 0], 0, footprint, 0),
        (17*slots-1, [0, 0, 3, 3], 63, 16*footprint, 112+(q-1)*k),
    ]
    for index, context, subarray, base, first in cases:
        actual = generator._output_placement(g, k, footprint, index)
        assert actual == (context, subarray, base, tuple(range(first, first+k)))
        assert base + footprint <= g["rows_per_subarray"]
        assert first // 16 == (first+k-1) // 16
        assert all(g["gb_successor"][mat] == mat+1 for mat in range(first, first+k-1))
    with pytest.raises(ValueError, match="one-rank placement capacity"):
        generator._output_placement(g, k, footprint, 17*slots)
    with pytest.raises(ValueError, match="local-row capacity"):
        generator._output_placement(g, k, 1025, 0)


def test_profile_edges_and_early_capacity_rejection():
    g = generator.placement_profile()
    successors = list(g["gb_successor"])
    successors[2] = -1
    with pytest.raises(ValueError, match="profile-supported"):
        generator._output_placement(g | {"gb_successor": successors}, 2, 60, 1)
    with patch.object(generator, "lower_to_physical") as lower:
        with pytest.raises(ValueError, match="one-rank placement capacity"):
            generator.generate("int8-gemv", 17*16*64*128+1, 12)
        with pytest.raises(ValueError, match="local-row capacity"):
            generator.generate("int8-gemv", 1, 8192*62)
        lower.assert_not_called()


def test_multiple_outputs_reuse_their_own_domain_range():
    metadata, trace = generator.generate("int8-gemv", 2, 8196)
    for index, record in enumerate(metadata["outputs"]):
        assert record["context"] == [0, 0, 0, 0]
        assert [d["mat_count"] for d in record["domains"]] == [16, 1]
        assert [d["mat_begin"] for d in record["domains"]] == [16*index]*2
        assert [d["sink_mat"] for d in record["domains"]] == [16*index+15, 16*index]
    matrix, vector = inputs("int8-gemv", 2, 8196)
    assert execute_trace(metadata, trace, matrix, vector) == scalar_graph("int8-gemv", matrix, vector)


@pytest.mark.parametrize("second_slot", [16, 128, 512, 2048, 131072])
def test_composition_at_capacity_contexts(second_slot):
    # Select a distant second slot without lowering all intervening outputs.
    place = generator._output_placement
    with patch.object(generator, "_output_placement",
                      side_effect=lambda g, k, f, i: place(g, k, f, second_slot if i else 0)):
        metadata, trace = generator.generate("int8-gemv", 2, 12)
    matrix, vector = inputs("int8-gemv", 2, 12)
    assert execute_trace(metadata, trace, matrix, vector) == scalar_graph("int8-gemv", matrix, vector)


@pytest.mark.parametrize("n", [0, -4, 1, 3, 7, 513, 515])
def test_reject_unsupported_tails(n):
    with pytest.raises(ValueError, match="N must"):
        generator.generate("int8-gemv", 1, n)
