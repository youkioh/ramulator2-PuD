"""Accepted representative HBM3 primitive model; see docs/pud/decisions.
Physical array, PRADA, selective close and internal transfer paths are hypothetical.
"""
import copy
from ramulator.dram.hbm3 import HBM3
from ramulator.dram.spec import TimingConstraint
from ramulator.param import Param
from ramulator.dram.pud import (
    COMPUTE_COMMANDS, COMPUTE_STATES, COMPUTE_TIMING_PARAMS,
    MOVEMENT_COMMANDS, MOVEMENT_STATES, compute_requests, movement_requests,
    compute_timing_constraints,
)

class HBM3_PuD(HBM3):
    name = "HBM3_PuD"
    levels = dict(HBM3.levels)
    commands = list(HBM3.commands) + list(COMPUTE_COMMANDS) + list(MOVEMENT_COMMANDS)
    states = list(HBM3.states) + list(COMPUTE_STATES) + list(MOVEMENT_STATES)
    timing_params = list(HBM3.timing_params) + list(COMPUTE_TIMING_PARAMS) + ["nRELOC"]
    supported_requests = dict(HBM3.supported_requests) | compute_requests() | movement_requests()
    row_commands = list(HBM3.row_commands) + list(COMPUTE_COMMANDS) + ["ACT_MOV"]
    column_commands = list(HBM3.column_commands) + ["RD_MOV", "WR_MOV"]
    command_cycles = dict(HBM3.command_cycles) | {
        "ACT_PUD": 1.5, "ACT_PUD_OC": 1.5, "ACT_PUD_S": 1.5,
        "ACT_PUD_S_OC": 1.5, "N": 0.5, "ACT_MOV": 1.5,
        "RD_MOV": 1, "WR_MOV": 1,
    }
    geometry = {"rows_per_subarray": 512}
    hffs_per_mat = Param(int, default=16)

    def to_config(self):
        config = super().to_config()
        config["hffs_per_mat"] = 16
        return config

    org_presets = {"HBM3_8Gb_8hi": dict(HBM3.org_presets["HBM3_8Gb_8hi"])}
    timing_presets = copy.deepcopy(HBM3.timing_presets)
    # Independent ceil(physical phase / 312.5 ps), expressed in CK here:
    # serializer converts once to half-ticks (29,13,106,90,112), relocation=4.
    timing_presets["HBM3_6400Mbps"].update(
        nPUD_ACT_OC=14.5, nPUD_ACT=6.5, nPUD_ACT_S_OC=53,
        nPUD_ACT_S=45, nPUD_N=56, nRELOC=2,
    )
    _open = ["ACT_PUD_OC", "ACT_PUD_S_OC", "ACT_MOV"]
    timing_constraints = copy.deepcopy(HBM3.timing_constraints) + compute_timing_constraints(
        local_level="Bank", close_command="PREpb",
    ) + [
        TimingConstraint("Bank", ["ACT_MOV"], ["PREpb", "WR_MOV"], "nRAS"),
        TimingConstraint("Bank", ["PREpb"], _open, "nRP"),
        TimingConstraint("Bank", ["ACT"], _open, "nRC"),
        TimingConstraint("Bank", ["RDA"], _open, "nRTP + nRP"),
        TimingConstraint("Bank", ["WRA"], _open, "nCWL + nBL + nWR + nRP"),
        TimingConstraint("PseudoChannel", ["PREab"], _open, "nRP"),
        TimingConstraint("PseudoChannel", ["REFab"], _open, "nRFC"),
        TimingConstraint("PseudoChannel", ["RFMab"], _open, "nRFMab"),
        TimingConstraint("PseudoChannel", ["REFpb", "RFMpb"], _open, "nRREFD"),
        TimingConstraint("Bank", ["REFpb"], _open, "nRFCpb"),
        TimingConstraint("Bank", ["RFMpb"], _open, "nRFMpb"),
    ]
