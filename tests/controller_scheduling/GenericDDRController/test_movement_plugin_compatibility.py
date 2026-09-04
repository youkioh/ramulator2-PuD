import pytest

import ramulator
import tests.controller_scheduling.harness as cs


pytestmark = pytest.mark.controller_scheduling


def make_dram(dram_class=ramulator.dram.DDR4_PuD_Movement):
    return dram_class(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )


def make_rit_mapper(*, reserved_rows_per_bank=0):
    return ramulator.addr_mapper.RITAddrMapper(
        reserved_rows_per_bank=reserved_rows_per_bank,
        addr_mapper=ramulator.addr_mapper.ChRaBaRoCo(),
    )


def make_aqua():
    return ramulator.controller_plugin.AQUA(
        num_art_entries=4,
        num_fpt_entries=4,
        num_qrows_per_bank=4,
        art_threshold=1024,
    )


def make_rrs():
    return ramulator.controller_plugin.RRS(
        num_hrt_entries=4,
        num_rit_entries=4,
        rss_threshold=1024,
    )


def operand(dut, *, row=0, column=0):
    return dut.addr_vec(
        Rank=0,
        BankGroup=0,
        Bank=0,
        Row=row,
        Column=column,
    )


def test_aqua_rejects_movement_capable_standard_at_setup():
    with pytest.raises(
        RuntimeError,
        match="AQUA is not compatible with movement-capable DRAM standards",
    ):
        cs.ControllerUnderTest.make_generic_ddr(
            make_dram(),
            addr_mapper=make_rit_mapper(reserved_rows_per_bank=4),
            controller_plugins=[make_aqua()],
        )


def test_rrs_rejects_movement_capable_standard_at_setup():
    with pytest.raises(
        RuntimeError,
        match="RRS is not compatible with movement-capable DRAM standards",
    ):
        cs.ControllerUnderTest.make_generic_ddr(
            make_dram(),
            addr_mapper=make_rit_mapper(),
            controller_plugins=[make_rrs()],
        )


@pytest.mark.parametrize(
    ("type_name", "mats", "expected"),
    [
        (
            "LC-MOV",
            (0, 0),
            ["ACT_MOV", "RD_MOV", "PREpb", "ACT_MOV", "WR_MOV", "PREpb"],
        ),
        (
            "GB-MOV",
            (0, 1),
            ["ACT_MOV", "ACT_MOV", "RD_MOV", "WR_MOV", "PREpb"],
        ),
    ],
)
def test_observational_plugin_receives_issued_movement_commands(
    type_name, mats, expected
):
    dut = cs.ControllerUnderTest.make_generic_ddr(
        make_dram(),
        controller_plugins=[
            ramulator.controller_plugin.IssuedCommandValidationHook()
        ],
    )
    dut.send_movement_request_for_testing(
        type_name,
        [operand(dut, row=10, column=3), operand(dut, row=11, column=5)],
        *mats,
        source_id=7,
    )

    history = dut.run_until_idle(max_ticks=256)

    assert [item.command for item in history] == expected
    assert all(item.source_id == 7 for item in history)


@pytest.mark.parametrize(
    ("plugin", "message"),
    [
        (
            ramulator.controller_plugin.PARA(threshold=0.5),
            "PARA is not compatible with the DRAM standard that does not have "
            r"Victim-Row-Refresh \(VRR\) command!",
        ),
        (
            ramulator.controller_plugin.RFMManager(rfm_mode="ab"),
            "RFMManager: rfm_mode='ab' requires DRAM standard with RFMab command",
        ),
    ],
)
def test_existing_unsupported_capability_rejections_are_preserved(plugin, message):
    with pytest.raises(RuntimeError, match=message):
        cs.ControllerUnderTest.make_generic_ddr(
            make_dram(),
            controller_plugins=[plugin],
        )


@pytest.mark.parametrize("dram_class", [ramulator.dram.DDR4, ramulator.dram.DDR4_PuD])
@pytest.mark.parametrize(
    ("plugin_factory", "mapper_factory"),
    [
        (make_aqua, lambda: make_rit_mapper(reserved_rows_per_bank=4)),
        (make_rrs, make_rit_mapper),
    ],
)
def test_aqua_and_rrs_remain_compatible_with_existing_ddr4_standards(
    dram_class, plugin_factory, mapper_factory
):
    dut = cs.ControllerUnderTest.make_generic_ddr(
        make_dram(dram_class),
        addr_mapper=mapper_factory(),
        controller_plugins=[plugin_factory()],
    )
    dut.priority_send("ACT", operand(dut, row=20))

    assert [item.command for item in dut.tick()] == ["ACT"]
