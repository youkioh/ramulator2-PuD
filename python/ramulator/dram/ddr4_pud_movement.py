import copy

from ramulator.dram.ddr4_pud import DDR4_PuD
from ramulator.param import Param


class DDR4_PuD_Movement(DDR4_PuD):
    """DDR4_PuD-derived substrate for the movement experiment."""

    name = "DDR4_PuD_Movement"

    # Keep every inherited mutable definition independent. Movement commands,
    # states, timings, and request mappings are added only in later phases.
    levels = copy.deepcopy(DDR4_PuD.levels)
    commands = copy.deepcopy(DDR4_PuD.commands)
    states = copy.deepcopy(DDR4_PuD.states)
    timing_params = copy.deepcopy(DDR4_PuD.timing_params)
    # Values are immutable strings or the shared controller-sequenced marker;
    # only the mutable mapping itself must be independent.
    supported_requests = dict(DDR4_PuD.supported_requests)
    timing_constraints = copy.deepcopy(DDR4_PuD.timing_constraints)
    command_cycles = copy.deepcopy(DDR4_PuD.command_cycles)
    row_commands = copy.deepcopy(DDR4_PuD.row_commands)
    column_commands = copy.deepcopy(DDR4_PuD.column_commands)
    org_presets = copy.deepcopy(DDR4_PuD.org_presets)
    timing_presets = copy.deepcopy(DDR4_PuD.timing_presets)
    geometry = copy.deepcopy(DDR4_PuD.geometry)

    hffs_per_mat = Param(int, default=4)

    def __init__(self, *, org_preset, timing_preset, hffs_per_mat=4, **overrides):
        if isinstance(hffs_per_mat, bool) or not isinstance(hffs_per_mat, int):
            raise TypeError("DDR4_PuD_Movement: hffs_per_mat must be an int")
        if hffs_per_mat <= 0:
            raise ValueError(
                f"DDR4_PuD_Movement: hffs_per_mat must be positive, got {hffs_per_mat}"
            )
        super().__init__(
            org_preset=org_preset,
            timing_preset=timing_preset,
            **overrides,
        )
        self.hffs_per_mat = hffs_per_mat

    def to_config(self):
        config = super().to_config()
        config["hffs_per_mat"] = self.hffs_per_mat
        return config
