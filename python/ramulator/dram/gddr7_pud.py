"""GDDR7 primitive substrate: Accepted G1/G2/G3/G4, project evaluation model.

Not vendor-calibrated circuitry or command encodings. Finite control engines,
movement current/DQ costs, payload simulation and SALP are outside this model.
"""
import copy

from ramulator.dram.gddr7 import GDDR7
from ramulator.dram.spec import TimingConstraint
from ramulator.param import Param
from ramulator.dram.pud import (
    COMPUTE_COMMANDS, COMPUTE_STATES, COMPUTE_TIMING_PARAMS,
    MOVEMENT_COMMANDS, MOVEMENT_STATES, compute_requests, movement_requests,
    compute_timing_constraints,
)


class GDDR7_PuD(GDDR7):
    name = "GDDR7_PuD"
    levels = dict(GDDR7.levels)
    commands = list(GDDR7.commands) + list(COMPUTE_COMMANDS) + list(MOVEMENT_COMMANDS)
    states = list(GDDR7.states) + list(COMPUTE_STATES) + list(MOVEMENT_STATES)
    timing_params = list(GDDR7.timing_params) + list(COMPUTE_TIMING_PARAMS) + ["nRELOC"]
    supported_requests = dict(GDDR7.supported_requests) | compute_requests() | movement_requests()
    row_commands = list(GDDR7.row_commands) + list(COMPUTE_COMMANDS) + ["ACT_MOV"]
    column_commands = list(GDDR7.column_commands) + ["RD_MOV", "WR_MOV"]
    command_cycles = dict(GDDR7.command_cycles) | {
        "ACT_PUD": 2, "ACT_PUD_OC": 2, "ACT_PUD_S": 2,
        "ACT_PUD_S_OC": 2, "N": 1, "ACT_MOV": 2, "RD_MOV": 2, "WR_MOV": 2,
    }
    geometry = {"rows_per_subarray": 512}
    hffs_per_mat = Param(int, default=8)

    def to_config(self):
        config = super().to_config()
        config["hffs_per_mat"] = 8
        return config

    org_presets = {"GDDR7_16Gb_x8": dict(GDDR7.org_presets["GDDR7_16Gb_x8"])}
    timing_presets = copy.deepcopy(GDDR7.timing_presets)
    # Policy A: ceil((9,4,32.992,27.992,35) ns / 0.571 ns), independently.
    # No ACT overhead envelope. Relocation is independently ceil(1/0.571).
    timing_presets["GDDR7_28000_PAM3"].update(
        nPUD_ACT_OC=16, nPUD_ACT=8, nPUD_ACT_S_OC=58,
        nPUD_ACT_S=50, nPUD_N=62, nRELOC=2,
    )
    _open = ["ACT_PUD_OC", "ACT_PUD_S_OC", "ACT_MOV"]
    timing_constraints = copy.deepcopy(GDDR7.timing_constraints) + compute_timing_constraints(
        local_level="Bank", close_command="PREpb",
    ) + [
        # Nominal final-reception intervals: spec.to_config adjusts once.
        TimingConstraint("Bank", ["ACT_MOV"], ["PREpb", "WR_MOV"], "nRAS"),
        TimingConstraint("Bank", ["PREpb"], _open, "nRP"),
        TimingConstraint("Bank", ["PREpb"], _open, "nRPD", sibling=True),
        TimingConstraint("Bank", ["RDA"], _open, "nRTPSB + nRP"),
        TimingConstraint("Bank", ["WRA"], _open, "nWL + nBL + nWR + nRP"),
        TimingConstraint("Channel", ["PREab"], _open, "nRP"),
        TimingConstraint("Channel", ["REFab"], _open, "nRFCab"),
        TimingConstraint("Channel", ["REFpb"], _open, "nRREFD"),
        TimingConstraint("Bank", ["REFpb"], _open, "nRFCpb"),
        TimingConstraint("Channel", ["RFMab"], _open, "nRFMab"),
        TimingConstraint("Bank", ["RFMpb"], _open, "nRFMpb"),
    ]
