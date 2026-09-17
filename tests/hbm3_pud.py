"""Direct Requests and independent HBM3 reception/edge timing calculations."""
from decimal import Decimal, ROUND_CEILING
import ramulator
from ramulator.dram.spec import REQUEST_TYPE_IDS
from ramulator._ramulator_test import _LocationResolverUnderTest, _LocatedSystemUnderTest, _located_request
from tests.unit_tests.test_pud_location import CONTEXT

ARITY = dict(RowCopy=2, MAJ3=3, MAJ5=5, NOT=1, NOT_COPY=2, **{"LC-MOV":2,"GB-MOV":2})
COMMANDS = {
    "RowCopy":["ACT_PUD_S_OC","ACT_PUD","PREpb"],
    "MAJ3":["ACT_PUD_OC","ACT_PUD","ACT_PUD_S","PREpb"],
    "MAJ5":["ACT_PUD_OC","ACT_PUD","ACT_PUD","ACT_PUD","ACT_PUD_S","PREpb"],
    "NOT":["ACT_PUD_S_OC","N","PREpb"],
    "NOT_COPY":["ACT_PUD_S_OC","N","ACT_PUD","PREpb"],
    "LC-MOV":["ACT_MOV","RD_MOV","PREpb","ACT_MOV","WR_MOV","PREpb"],
    "GB-MOV":["ACT_MOV","ACT_MOV","RD_MOV","WR_MOV","PREpb"],
}
OCC = {c: (3 if c.startswith("ACT") else 2 if c in ("RD_MOV","WR_MOV") else 1)
       for seq in COMMANDS.values() for c in seq}
PHASE = {c:int((Decimal(ns)/Decimal("0.3125")).to_integral_value(rounding=ROUND_CEILING))
         for c,ns in zip(["ACT_PUD_OC","ACT_PUD","ACT_PUD_S_OC","ACT_PUD_S","N"],
                         ["9","4","32.992","27.992","35"])}

def timeline(name, destinations=1, edges=True):
    cmds = COMMANDS[name]
    if name == "RowCopy": cmds = [cmds[0]]+["ACT_PUD"]*destinations+["PREpb"]
    dependencies = ([(0,1,62),(1,2,18),(0,2,90),(2,3,52),(3,4,90),(4,5,70),(3,5,90)]
        if name=="LC-MOV" else
        [(0,2,90),(1,3,90),(2,3,4),(3,4,66),(1,4,90)]
        if name=="GB-MOV" else [(i,i+1,PHASE[c]) for i,c in enumerate(cmds[:-1])])
    clocks = []
    buses = {"row":0,"col":0}
    last_row = None
    for i,c in enumerate(cmds):
        bus = "col" if c in ("RD_MOV","WR_MOV") else "row"
        t = max(1 if edges else 0, buses[bus], clocks[-1] if clocks else 0)
        for a,b,nominal in dependencies:
            if b==i: t=max(t,clocks[a]+nominal+OCC[cmds[a]]-OCC[c])
        if edges:
            if c != "PREpb": t += int(t%2==0)
            elif t%2==0 and last_row is not None:
                previous,issued = last_row
                if t == issued+(3 if previous.startswith("ACT") else 1): t+=1
        clocks.append(t)
        buses[bus]=t+OCC[c]
        if edges and bus=="row" and t%2: last_row=(c,t)
    return cmds,clocks,clocks[-1]+52

def dram():
    return ramulator.dram.HBM3_PuD(org_preset="HBM3_8Gb_8hi",timing_preset="HBM3_6400Mbps").to_config()

def resolver(config=None):
    return _LocationResolverUnderTest(config or dram(),CONTEXT,{})

def controller_config(scheduler="FRFCFS",refresh="NoRefresh",**options):
    return dict(impl="HBM34",dram=dram(),scheduler=dict(impl=scheduler),
        refresh_manager=dict(impl=refresh),row_policy=dict(impl="Open"),
        addr_mapper=dict(impl="RoBaRaCoCh"),pud_placement_profile="MIMDRAM_HBM3_8Gb_8hi_v1",**options)

def system(scheduler="FRFCFS",refresh="NoRefresh",**options):
    return _LocatedSystemUnderTest(controller_config(scheduler,refresh,**options),resolver(),install=False)

def request(owner,name="RowCopy",mats=(0,0),bank=0,pc=0,sid=0,bg=0,row=10,destinations=1):
    movement=name in ("LC-MOV","GB-MOV")
    count=destinations+1 if name=="RowCopy" else ARITY[name]
    desc=[]
    for i in range(count):
        selected=(mats[0]+i,mats[0]+i) if name=="GB-MOV" else mats
        d=dict(kind="group" if movement else "compute",
               row=[0,pc,sid,bg,bank,row+i],range=list(selected))
        if movement: d["group"]=i+3
        desc.append(d)
    args=(REQUEST_TYPE_IDS[name],desc,-1 if movement else 32)
    return owner.request(*args) if hasattr(owner,"request") else _located_request(owner,*args)

def events(d,source):
    return [e for e in d.issued() if e["source_id"]==source]
def times(d,source):
    return [e["clk"] for e in events(d,source)]
