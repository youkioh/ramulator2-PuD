"""Accepted evaluation presets; all placement geometry comes from C++ profiles."""
import ramulator

TARGETS = ("DDR4", "GDDR7", "HBM3", "DDR4-packed")


def target_config(target):
    if target in ("DDR4", "DDR4-packed"):
        return dict(dram=ramulator.dram.DDR4_PuD_Movement(
            org_preset="DDR4_8Gb_x8", timing_preset="DDR4_2400R", rank=1, hffs_per_mat=4),
            controller="GenericDDR", channels=1, profile="MIMDRAM_DDR4_8Gb_x8_v1",
            organization="DDR4_8Gb_x8", refresh="NoRefresh", tick_unit="CK",
            evaluation_unit="one 64-bit Channel/rank, eight x8 chips")
    if target == "GDDR7":
        return dict(dram=ramulator.dram.GDDR7_PuD(
            org_preset="GDDR7_16Gb_x8", timing_preset="GDDR7_28000_PAM3"),
            controller="GDDR7", channels=4, profile="MIMDRAM_GDDR7_16Gb_x8_v1",
            organization="GDDR7_16Gb_x8", refresh="AllBank", tick_unit="CK4",
            evaluation_unit="one GDDR7 x32 device, four independent x8 Channels")
    if target == "HBM3":
        return dict(dram=ramulator.dram.HBM3_PuD(
            org_preset="HBM3_8Gb_8hi", timing_preset="HBM3_6400Mbps"),
            controller="HBM34", channels=16, profile="MIMDRAM_HBM3_8Gb_8hi_v1",
            organization="HBM3_8Gb_8hi", refresh="AllBank", tick_unit="half-CK",
            evaluation_unit="one selected HBM3 stack, sixteen Channels with two PCs each")
    raise ValueError(f"unsupported GEMV target: {target}")
