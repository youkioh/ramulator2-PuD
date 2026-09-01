from ramulator.dram.ddr4 import DDR4
from ramulator.dram.spec import CONTROLLER_SEQUENCED, TimingConstraint


class DDR4_PuD(DDR4):
    """DDR4 baseline substrate reserved for PuD extensions."""

    name = "DDR4_PuD"

    # Keep every mutable definition independent before PuD extends it.
    levels = dict(DDR4.levels)
    commands = list(DDR4.commands) + [
        "ACT_PUD",
        "ACT_PUD_OC",
        "ACT_PUD_S",
        "ACT_PUD_S_OC",
        "N",
    ]
    states = list(DDR4.states) + ["PuDChargeSharing", "PuDSensed"]
    timing_params = list(DDR4.timing_params) + [
        "nPUD_ACT_OC",
        "nPUD_ACT",
        "nPUD_ACT_S_OC",
        "nPUD_ACT_S",
        "nPUD_N",
    ]
    supported_requests = dict(DDR4.supported_requests)
    supported_requests.update(
        {
            "RowCopy": CONTROLLER_SEQUENCED,
            "MAJ3": CONTROLLER_SEQUENCED,
            "MAJ5": CONTROLLER_SEQUENCED,
            "NOT": CONTROLLER_SEQUENCED,
        }
    )
    timing_constraints = list(DDR4.timing_constraints) + [
        # PuD phase timing is target-bank-local. Each value is independently
        # ceiling-converted for the DDR4_2400R baseline by Decision Gate 8.
        TimingConstraint(
            level="Bank",
            preceding=["ACT_PUD_OC"],
            following=["ACT_PUD"],
            latency="nPUD_ACT_OC",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["ACT_PUD"],
            following=["ACT_PUD", "ACT_PUD_S", "PREpb"],
            latency="nPUD_ACT",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["ACT_PUD_S_OC"],
            following=["ACT_PUD", "N"],
            latency="nPUD_ACT_S_OC",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["ACT_PUD_S"],
            following=["PREpb"],
            latency="nPUD_ACT_S",
        ),
        TimingConstraint(
            level="Bank",
            preceding=["N"],
            following=["PREpb"],
            latency="nPUD_N",
        ),
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
