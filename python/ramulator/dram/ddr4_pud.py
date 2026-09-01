from ramulator.dram.ddr4 import DDR4
from ramulator.dram.spec import CONTROLLER_SEQUENCED


class DDR4_PuD(DDR4):
    """DDR4 baseline substrate reserved for PuD extensions."""

    name = "DDR4_PuD"

    # Keep every mutable definition independent before PuD extends it.
    levels = dict(DDR4.levels)
    commands = list(DDR4.commands)
    states = list(DDR4.states)
    timing_params = list(DDR4.timing_params)
    supported_requests = dict(DDR4.supported_requests)
    supported_requests.update({
        "RowCopy": CONTROLLER_SEQUENCED,
        "MAJ3": CONTROLLER_SEQUENCED,
        "MAJ5": CONTROLLER_SEQUENCED,
        "NOT": CONTROLLER_SEQUENCED,
    })
    timing_constraints = list(DDR4.timing_constraints)
    command_cycles = dict(DDR4.command_cycles)
    row_commands = list(DDR4.row_commands)
    column_commands = list(DDR4.column_commands)
    org_presets = {name: dict(values) for name, values in DDR4.org_presets.items()}
    timing_presets = {name: dict(values) for name, values in DDR4.timing_presets.items()}
    geometry = {"rows_per_subarray": 1024}
