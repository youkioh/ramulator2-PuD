"""Direct-Request fixtures and independent Accepted G2/G4 timing oracle."""
from decimal import Decimal, ROUND_CEILING
import ramulator
from ramulator.dram.spec import REQUEST_TYPE_IDS
from ramulator._ramulator_test import _LocationResolverUnderTest, _LocatedSystemUnderTest, _located_request
from tests.unit_tests.test_pud_location import CONTEXT

ARITY = dict(RowCopy=2, MAJ3=3, MAJ5=5, NOT=1, NOT_COPY=2, **{"LC-MOV": 2, "GB-MOV": 2})
COMMANDS = {
    "RowCopy": ["ACT_PUD_S_OC", "ACT_PUD", "PREpb"],
    "MAJ3": ["ACT_PUD_OC", "ACT_PUD", "ACT_PUD_S", "PREpb"],
    "MAJ5": ["ACT_PUD_OC", "ACT_PUD", "ACT_PUD", "ACT_PUD", "ACT_PUD_S", "PREpb"],
    "NOT": ["ACT_PUD_S_OC", "N", "PREpb"],
    "NOT_COPY": ["ACT_PUD_S_OC", "N", "ACT_PUD", "PREpb"],
    "LC-MOV": ["ACT_MOV", "RD_MOV", "PREpb", "ACT_MOV", "WR_MOV", "PREpb"],
    "GB-MOV": ["ACT_MOV", "ACT_MOV", "RD_MOV", "WR_MOV", "PREpb"],
}
OCCUPANCY = {c: (1 if c in ("PREpb", "N") else 2) for seq in COMMANDS.values() for c in seq}
PHASE = {c: int((Decimal(ns)/Decimal("0.571")).to_integral_value(rounding=ROUND_CEILING))
         for c, ns in zip(["ACT_PUD_OC", "ACT_PUD", "ACT_PUD_S_OC", "ACT_PUD_S", "N"],
                          ["9", "4", "32.992", "27.992", "35"])}


def timeline(name, destinations=1):
    commands = COMMANDS[name]
    if name == "RowCopy":
        commands = ["ACT_PUD_S_OC"] + ["ACT_PUD"] * destinations + ["PREpb"]
    if name == "LC-MOV":
        # max(ACT minimum active, read-close); reception-converted source PRE.
        clocks = [0, 30, max(60+2-1, 30+4+2-1)]
        clocks += [clocks[-1]+30+1-2]
        clocks += [clocks[-1]+60]
        clocks += [clocks[-1]+2+30+2-1]
    elif name == "GB-MOV":
        clocks = [0, 2, 60]
        clocks += [max(clocks[1]+60, clocks[2]+2)]
        clocks += [max(clocks[1]+60+2-1, clocks[3]+30+2-1)]
    else:
        clocks = [0]
        for prev, follow in zip(commands, commands[1:]):
            clocks.append(clocks[-1] + PHASE[prev] + OCCUPANCY[prev] - OCCUPANCY[follow])
    return commands, clocks, clocks[-1]+30


def dram():
    return ramulator.dram.GDDR7_PuD(org_preset="GDDR7_16Gb_x8", timing_preset="GDDR7_28000_PAM3").to_config()


def resolver(config=None):
    return _LocationResolverUnderTest(config or dram(), CONTEXT, {})


def controller_config(scheduler="FRFCFS", mode="always_on", refresh="NoRefresh", **options):
    return dict(impl="GDDR7", dram=dram(), scheduler=dict(impl=scheduler),
               refresh_manager=dict(impl=refresh), row_policy=dict(impl="Open"),
               addr_mapper=dict(impl="RoBaRaCoCh"), rck_mode=mode,
               pud_placement_profile="MIMDRAM_GDDR7_16Gb_x8_v1", **options)


def system(scheduler="FRFCFS", mode="always_on", refresh="NoRefresh", **options):
    return _LocatedSystemUnderTest(controller_config(scheduler, mode, refresh, **options), resolver(), install=False)


def request(owner, name="RowCopy", mats=(0, 0), bank=0, row=10, destinations=1):
    movement = name in ("LC-MOV", "GB-MOV")
    count = destinations+1 if name == "RowCopy" else ARITY[name]
    desc = []
    for i in range(count):
        selected = (mats[0]+i, mats[0]+i) if name == "GB-MOV" else mats
        d = dict(kind="group" if movement else "compute", row=[0, bank, row+i], range=list(selected))
        if movement: d["group"] = i+3
        desc.append(d)
    args = (REQUEST_TYPE_IDS[name], desc, -1 if movement else 32)
    return owner.request(*args) if hasattr(owner, "request") else _located_request(owner, *args)


def events(d, source):
    return [e for e in d.issued() if e["source_id"] == source]


def times(d, source):
    return [e["clk"] for e in events(d, source)]
