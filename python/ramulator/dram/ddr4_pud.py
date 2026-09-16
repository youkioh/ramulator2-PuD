from ramulator.dram.ddr4 import DDR4
from ramulator.dram.spec import TimingConstraint
from ramulator.dram.pud import (
    COMPUTE_COMMANDS, COMPUTE_STATES, COMPUTE_TIMING_PARAMS,
    compute_requests, compute_timing_constraints,
)


class DDR4_PuD(DDR4):
    """Reusable DDR4 PuD compute command and timing definitions."""

    name = "DDR4_PuD"

    # Keep every mutable definition independent before PuD extends it.
    levels = dict(DDR4.levels)
    commands = list(DDR4.commands) + list(COMPUTE_COMMANDS)
    states = list(DDR4.states) + list(COMPUTE_STATES)
    timing_params = list(DDR4.timing_params) + list(COMPUTE_TIMING_PARAMS)
    supported_requests = dict(DDR4.supported_requests)
    supported_requests.update(compute_requests())
    timing_constraints = list(DDR4.timing_constraints) + compute_timing_constraints(
        local_level="Bank", close_command="PREpb",
    ) + [
        # Conventional close and refresh recovery before either PuD opening
        # command follows the corresponding existing DDR4 ACT constraint.
        TimingConstraint(
            level="Rank",
            preceding=["PREab"],
            following=["ACT_PUD_OC", "ACT_PUD_S_OC"],
            latency="nRP",
        ),
        TimingConstraint(
            level="Rank",
            preceding=["REFab"],
            following=["ACT_PUD_OC", "ACT_PUD_S_OC"],
            latency="nRFC",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["PREpb"],
            following=["ACT_PUD_OC", "ACT_PUD_S_OC"],
            latency="nRP",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["RDA"],
            following=["ACT_PUD_OC", "ACT_PUD_S_OC"],
            latency="nRTP + nRP",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["WRA"],
            following=["ACT_PUD_OC", "ACT_PUD_S_OC"],
            latency="nCWL + nBL + nWR + nRP",
        ),
    ]
    command_cycles = dict(DDR4.command_cycles)
    row_commands = list(DDR4.row_commands)
    column_commands = list(DDR4.column_commands)
    org_presets = {name: dict(values) for name, values in DDR4.org_presets.items()}
    timing_presets = {
        "DDR4_2400R": {
            **DDR4.timing_presets["DDR4_2400R"],
            "nPUD_ACT_OC": 11,
            "nPUD_ACT": 5,
            "nPUD_ACT_S_OC": 40,
            "nPUD_ACT_S": 34,
            "nPUD_N": 43,
        }
    }
    geometry = {"rows_per_subarray": 1024}
