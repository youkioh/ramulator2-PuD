"""Export-only configuration for the DDR4_PuD C++ microbenchmark."""

import os
import ramulator

v2 = os.environ.get("RAMULATOR_PUD_V2") == "1"
frontend = ramulator.frontend.External(clock_ratio=1, num_cores=105)

dram = (ramulator.dram.DDR4_PuD_Movement if v2 else ramulator.dram.DDR4_PuD)(
    org_preset="DDR4_8Gb_x8",
    timing_preset="DDR4_2400R",
    rank=1,
)
controller = ramulator.controller.GenericDDR(
    dram=dram,
    pud_buffer_size=32 if v2 else 1,
    **(dict(pud_placement_profile="MIMDRAM_DDR4_8Gb_x8_v1",
            pud_compute_engines=int(os.environ.get("RAMULATOR_PUD_ENGINES", "8"))) if v2 else {}),
    scheduler=ramulator.scheduler.FRFCFS(),
    refresh_manager=ramulator.refresh_manager.NoRefresh(),
    row_policy=ramulator.row_policy.Open(),
    addr_mapper=ramulator.addr_mapper.RoBaRaCoCh() if v2 else ramulator.addr_mapper.PassThroughAddrMapper(),
    controller_plugins=[
        ramulator.controller_plugin.CmdTraceRecorder(
            path="build/ddr4_pud_trace.csv",
        ),
    ],
)
memory_system = ramulator.memory_system.GenericDRAM(
    clock_ratio=1,
    controllers=[controller],
    channel_mapper=ramulator.channel_mapper.CacheLineInterleave() if v2 else ramulator.channel_mapper.PassThroughChannelMapper(),
)

# `ramulator export` captures this component tree without running a simulation.
simulation = ramulator.Simulation(frontend, memory_system)
