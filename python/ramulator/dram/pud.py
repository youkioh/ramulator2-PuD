"""Common PuD declarations; no standard, geometry, calibration or bus policy.

Bindings choose command placement and numeric timing. These functions return
fresh mutable definitions, preserving the inherited-standard isolation contract.
"""
from ramulator.dram.spec import CONTROLLER_SEQUENCED, TimingConstraint

COMPUTE_COMMANDS = ("ACT_PUD", "ACT_PUD_OC", "ACT_PUD_S", "ACT_PUD_S_OC", "N")
COMPUTE_STATES = ("PuDChargeSharing", "PuDSensed")
COMPUTE_TIMING_PARAMS = (
    "nPUD_ACT_OC", "nPUD_ACT", "nPUD_ACT_S_OC", "nPUD_ACT_S", "nPUD_N",
)
MOVEMENT_COMMANDS = ("ACT_MOV", "RD_MOV", "WR_MOV")
MOVEMENT_STATES = ("MovementActive", "MovementDataValid")


def compute_requests():
    return dict.fromkeys(("RowCopy", "MAJ3", "MAJ5", "NOT", "NOT_COPY"), CONTROLLER_SEQUENCED)


def movement_requests():
    return dict.fromkeys(("LC-MOV", "GB-MOV"), CONTROLLER_SEQUENCED)


def compute_timing_constraints(*, local_level, close_command):
    """PRADA phase dependencies; each binding supplies its calibrated values."""
    return [
        TimingConstraint(local_level, ["ACT_PUD_OC"], ["ACT_PUD"], "nPUD_ACT_OC"),
        TimingConstraint(local_level, ["ACT_PUD"], ["ACT_PUD", "ACT_PUD_S", close_command], "nPUD_ACT"),
        TimingConstraint(local_level, ["ACT_PUD_S_OC"], ["ACT_PUD", "N"], "nPUD_ACT_S_OC"),
        TimingConstraint(local_level, ["ACT_PUD_S"], [close_command], "nPUD_ACT_S"),
        TimingConstraint(local_level, ["N"], ["ACT_PUD", close_command], "nPUD_N"),
    ]
