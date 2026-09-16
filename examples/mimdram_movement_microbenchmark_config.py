"""Export-only configuration for focused movement validation on canonical DDR4 PuD."""

import ramulator

frontend = ramulator.frontend.External(clock_ratio=1, num_cores=206)

dram = ramulator.dram.DDR4_PuD_Movement(
    org_preset="DDR4_8Gb_x8",
    timing_preset="DDR4_2400R",
    rank=1,
    hffs_per_mat=4,
)
controller = ramulator.controller.GenericDDR(
    dram=dram,
    pud_buffer_size=32,
    pud_placement_profile="MIMDRAM_DDR4_8Gb_x8_v1",
    scheduler=ramulator.scheduler.FRFCFS(),
    refresh_manager=ramulator.refresh_manager.NoRefresh(),
    row_policy=ramulator.row_policy.Open(),
    addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
    controller_plugins=[
        ramulator.controller_plugin.CmdTraceRecorder(
            # The benchmark replaces this base path for each isolated case.
            path="build/mimdram_movement_trace",
        ),
    ],
)
memory_system = ramulator.memory_system.GenericDRAM(
    clock_ratio=1,
    controllers=[controller],
    channel_mapper=ramulator.channel_mapper.CacheLineInterleave(),
)

# `ramulator export` captures this component tree without running a simulation.
simulation = ramulator.Simulation(frontend, memory_system)
