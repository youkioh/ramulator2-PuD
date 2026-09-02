"""Export-only configuration for the DDR4_PuD C++ microbenchmark."""

import ramulator

frontend = ramulator.frontend.External(clock_ratio=1)

dram = ramulator.dram.DDR4_PuD(
    org_preset="DDR4_8Gb_x8",
    timing_preset="DDR4_2400R",
    rank=1,
)
controller = ramulator.controller.GenericDDR(
    dram=dram,
    pud_buffer_size=1,
    scheduler=ramulator.scheduler.FRFCFS(),
    refresh_manager=ramulator.refresh_manager.NoRefresh(),
    row_policy=ramulator.row_policy.Open(),
    addr_mapper=ramulator.addr_mapper.PassThroughAddrMapper(),
    controller_plugins=[
        ramulator.controller_plugin.CmdTraceRecorder(
            path="build/ddr4_pud_trace.csv",
        ),
    ],
)
memory_system = ramulator.memory_system.GenericDRAM(
    clock_ratio=1,
    controllers=[controller],
    channel_mapper=ramulator.channel_mapper.PassThroughChannelMapper(),
)

# `ramulator export` captures this component tree without running a simulation.
simulation = ramulator.Simulation(frontend, memory_system)
