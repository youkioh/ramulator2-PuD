"""Focused composition cases; existing suites own primitive validation."""
from collections import Counter
from unittest.mock import patch
import pytest
from tools.pud_operation_generator.requirements import operation_requirements as micro_operation_requirements
from . import generator
from .validation import execute_trace, scalar_graph

CASES = [(1, 4), (1, 512), (1, 1024), (1, 1536), (1, 516), (2, 12), (2, 1028), (1, 8196)]


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
    for record in metadata["outputs"]:
        ownership = [set(range(first, first+8)) for first in record["macro_operation_temporary_row_bases"].values()]
        ownership += [set(record["micro_operation_temporary_rows"]), set(record["constant_rows"].values())]
        ownership += [set(range(first, first+8)) for pair in record["input_rows"] for first in pair]
        assert sum(map(len, ownership)) == len(set.union(*ownership))
        terms = []
        start = 0
        for domain in record["domains"]:
            assert domain["sink_mat"] == domain["mat_count"]-1
            for mat in range(domain["mat_count"]):
                terms.extend(start+mat*512+lane for lane in range(min(512, domain["elements"]-mat*512)))
            start += domain["elements"]
        assert terms == list(range(n))
    for line in trace:
        fields = line.split()
        if fields[0] == "GB-MOV":
            assert geometry["gb_successor"][int(fields[5])] == int(fields[6])


@pytest.mark.parametrize("n", [0, -4, 1, 3, 7, 513, 515])
def test_reject_unsupported_tails(n):
    with pytest.raises(ValueError, match="N must"):
        generator.generate("int8-gemv", 1, n)
