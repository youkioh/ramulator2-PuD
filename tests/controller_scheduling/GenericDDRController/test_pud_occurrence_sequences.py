import pytest
from ramulator._ramulator_test import _exercise_pud_sequence
from ramulator.dram.spec import REQUEST_TYPE_IDS

import ramulator
import tests.controller_scheduling.harness as cs

pytestmark = pytest.mark.controller_scheduling


def make_dram(*, movement):
    dram_class = ramulator.dram.DDR4_PuD_Movement if movement else ramulator.dram.DDR4_PuD
    return dram_class(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )


def operands(rows):
    return [[0, 0, 0, 0, row, column] for column, row in enumerate(rows)]


def exercise(dram, type_name, request_operands, commands, clocks=None):
    clocks = list(range(len(commands))) if clocks is None else clocks
    return _exercise_pud_sequence(
        dram.to_config(),
        REQUEST_TYPE_IDS[type_name],
        request_operands,
        commands,
        clocks,
    )


@pytest.mark.parametrize(
    ("type_name", "rows", "commands", "operand_indices"),
    [
        ("RowCopy", [10, 11], ["ACT_PUD_S_OC", "ACT_PUD", "PREpb"], [0, 1, 1]),
        (
            "RowCopy",
            [20, 21, 22, 23],
            ["ACT_PUD_S_OC", "ACT_PUD", "ACT_PUD", "ACT_PUD", "PREpb"],
            [0, 1, 2, 3, 3],
        ),
        ("MAJ3", [30, 31, 32], ["ACT_PUD_OC", "ACT_PUD", "ACT_PUD_S", "PREpb"], [0, 1, 2, 2]),
        (
            "MAJ5",
            [40, 41, 42, 43, 44],
            ["ACT_PUD_OC", "ACT_PUD", "ACT_PUD", "ACT_PUD", "ACT_PUD_S", "PREpb"],
            [0, 1, 2, 3, 4, 4],
        ),
        ("NOT", [50], ["ACT_PUD_S_OC", "N", "PREpb"], [0, 0, 0]),
    ],
)
def test_inherited_pud_occurrence_descriptors_are_unchanged(
    type_name, rows, commands, operand_indices
):
    dram = make_dram(movement=False)
    request_operands = operands(rows)

    result = exercise(dram, type_name, request_operands, commands)
    descriptors = result["descriptors"]

    assert [item["command"] for item in descriptors] == commands
    assert [item["operand_index"] for item in descriptors] == operand_indices
    assert [item["addr_vec"] for item in descriptors] == [
        request_operands[index] for index in operand_indices
    ]
    assert [item["index"] for item in descriptors] == list(range(len(commands)))
    assert [item["terminal"] for item in descriptors] == [
        *([False] * (len(commands) - 1)),
        True,
    ]
    assert result["cursor"] == len(commands)
    assert result["history"] == list(range(len(commands)))


@pytest.mark.parametrize(
    ("type_name", "commands", "operand_indices", "roles"),
    [
        (
            "LC-MOV",
            ["ACT_MOV", "RD_MOV", "PREpb", "ACT_MOV", "WR_MOV", "PREpb"],
            [0, 0, 0, 1, 1, 1],
            ["source", "source", "source", "destination", "destination", "destination"],
        ),
        (
            "GB-MOV",
            ["ACT_MOV", "ACT_MOV", "RD_MOV", "WR_MOV", "PREpb"],
            [0, 1, 0, 1, 1],
            ["source", "destination", "source", "destination", "destination"],
        ),
    ],
)
def test_movement_occurrence_descriptors_and_copy_safe_history(
    type_name, commands, operand_indices, roles
):
    dram = make_dram(movement=True)
    request_operands = operands([100, 101])
    issue_clks = [10 + index * 7 for index in range(len(commands))]

    result = exercise(dram, type_name, request_operands, commands, issue_clks)
    descriptors = result["descriptors"]

    assert [item["command"] for item in descriptors] == commands
    assert [item["operand_index"] for item in descriptors] == operand_indices
    assert [item["addr_vec"] for item in descriptors] == [
        request_operands[index] for index in operand_indices
    ]
    assert [item["role"] for item in descriptors] == roles
    assert [item["index"] for item in descriptors] == list(range(len(commands)))
    assert [item["terminal"] for item in descriptors] == [
        *([False] * (len(commands) - 1)),
        True,
    ]
    assert result["cursor"] == len(commands)
    assert result["history"] == issue_clks


def test_preparatory_precharge_does_not_advance_or_record_movement_occurrence():
    dram = make_dram(movement=True)
    commands = ["ACT_MOV", "RD_MOV", "PREpb", "ACT_MOV", "WR_MOV", "PREpb"]
    issue_clks = [4, 10, 20, 30, 40, 50, 60]

    result = exercise(
        dram,
        "LC-MOV",
        operands([200, 201]),
        ["PREpb", *commands],
        issue_clks,
    )

    preparatory = result["events"][0]
    assert preparatory == {
        "cursor_before": 0,
        "cursor_after": 0,
        "history": [-1] * len(commands),
        "progress": "not_issued",
    }
    assert result["history"] == issue_clks[1:]


def test_movement_descriptors_share_semantic_command_ids_and_mappings_are_enabled():
    dram = make_dram(movement=True)
    request_operands = operands([300, 301])
    lc_commands = ["ACT_MOV", "RD_MOV", "PREpb", "ACT_MOV", "WR_MOV", "PREpb"]
    gb_commands = ["ACT_MOV", "ACT_MOV", "RD_MOV", "WR_MOV", "PREpb"]

    lc = exercise(dram, "LC-MOV", request_operands, lc_commands)["descriptors"]
    gb = exercise(dram, "GB-MOV", request_operands, gb_commands)["descriptors"]

    assert lc[0]["command"] == lc[3]["command"] == "ACT_MOV"
    assert gb[0]["command"] == gb[1]["command"] == "ACT_MOV"
    assert lc[0]["command"] == gb[0]["command"]
    assert lc[1]["command"] == gb[2]["command"] == "RD_MOV"
    assert lc[4]["command"] == gb[3]["command"] == "WR_MOV"
    assert "LC-MOV" in dram.supported_requests
    assert "GB-MOV" in dram.supported_requests


def test_occurrence_history_survives_real_controller_promotion_and_completion_copy():
    dram = make_dram(movement=False)
    dut = cs.ControllerUnderTest.make_generic_ddr(
        dram,
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
        row_policy=ramulator.row_policy.Open(),
    )

    dut.send_pud_request("RowCopy", operands([400, 401]), source_id=9)
    history = dut.run_until_idle(max_ticks=256)

    assert dut.completion_occurrence_histories() == [
        [item.clk for item in history]
    ]
