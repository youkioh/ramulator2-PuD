import copy

import pytest

import ramulator
from ramulator._ramulator_test import _DeviceUnderTest


def make_dram(dram_class=ramulator.dram.DDR4_PuD_Movement, **kwargs):
    return dram_class(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
        **kwargs,
    )


def test_combined_skeleton_configuration_matches_ddr4_pud():
    baseline = make_dram(ramulator.dram.DDR4_PuD).to_config()
    combined = make_dram().to_config()

    assert combined.pop("impl") == "DDR4_PuD_Movement"
    assert combined.pop("hffs_per_mat") == 4
    baseline.pop("impl")
    assert combined == baseline

    baseline_dut = _DeviceUnderTest(make_dram(ramulator.dram.DDR4_PuD).to_config())
    combined_dut = _DeviceUnderTest(make_dram().to_config())
    assert combined_dut.level_names == baseline_dut.level_names
    assert combined_dut.command_names == baseline_dut.command_names
    assert combined_dut.state_names == baseline_dut.state_names
    assert combined_dut.timings == baseline_dut.timings
    assert combined_dut.supports_inherited_pud_requests() is True
    assert combined_dut.supports_movement_requests() is False


def test_combined_mutable_definitions_are_independent_from_both_bases():
    mutable_names = (
        "levels",
        "commands",
        "states",
        "timing_params",
        "supported_requests",
        "timing_constraints",
        "command_cycles",
        "row_commands",
        "column_commands",
        "org_presets",
        "timing_presets",
        "geometry",
    )

    for name in mutable_names:
        combined = getattr(ramulator.dram.DDR4_PuD_Movement, name)
        assert combined is not getattr(ramulator.dram.DDR4_PuD, name)
        assert combined is not getattr(ramulator.dram.DDR4, name)

    assert all(
        combined_tc is not baseline_tc
        for combined_tc, baseline_tc in zip(
            ramulator.dram.DDR4_PuD_Movement.timing_constraints,
            ramulator.dram.DDR4_PuD.timing_constraints,
        )
    )

    definitions = copy.deepcopy(ramulator.dram.DDR4_PuD_Movement.commands)
    ramulator.dram.DDR4_PuD_Movement.commands.append("TEST_ONLY")
    try:
        assert "TEST_ONLY" not in ramulator.dram.DDR4_PuD.commands
        assert "TEST_ONLY" not in ramulator.dram.DDR4.commands
    finally:
        ramulator.dram.DDR4_PuD_Movement.commands = definitions


def test_hffs_per_mat_default_and_positive_override_reach_device():
    default_dut = _DeviceUnderTest(make_dram().to_config())
    override_dut = _DeviceUnderTest(make_dram(hffs_per_mat=8).to_config())

    assert default_dut.supports_hffs_per_mat_config is True
    assert default_dut.hffs_per_mat == 4
    assert override_dut.hffs_per_mat == 8


@pytest.mark.parametrize("value", (0, -1))
def test_hffs_per_mat_rejects_non_positive_values(value):
    with pytest.raises(ValueError, match="hffs_per_mat must be positive"):
        make_dram(hffs_per_mat=value)

    config = make_dram().to_config()
    config["hffs_per_mat"] = value
    with pytest.raises(RuntimeError, match="hffs_per_mat must be positive"):
        _DeviceUnderTest(config)


def test_hffs_per_mat_rejects_non_integer_values():
    with pytest.raises(TypeError, match="hffs_per_mat must be an int"):
        make_dram(hffs_per_mat=4.0)


@pytest.mark.parametrize("dram_class", (ramulator.dram.DDR4, ramulator.dram.DDR4_PuD))
def test_hffs_per_mat_is_absent_and_unsupported_on_existing_standards(dram_class):
    config = make_dram(dram_class).to_config()
    assert "hffs_per_mat" not in config

    dut = _DeviceUnderTest(config)
    assert dut.supports_hffs_per_mat_config is False
    assert dut.hffs_per_mat == -1

    config["hffs_per_mat"] = 4
    with pytest.raises(RuntimeError, match="hffs_per_mat is unsupported"):
        _DeviceUnderTest(config)
