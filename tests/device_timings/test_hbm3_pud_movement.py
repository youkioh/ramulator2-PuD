import pytest
from ramulator._ramulator_test import _ComputeRangesUnderTest, _located_request
from ramulator.dram.spec import REQUEST_TYPE_IDS
from tests.hbm3_pud import dram,resolver,request,timeline,system
from tests.device_timings.test_pud_compute_ranges import issue

@pytest.mark.parametrize("name,mats",[
    ("LC-MOV",(0,0)),("LC-MOV",(7,8)),("LC-MOV",(0,15)),
    ("GB-MOV",(0,0)),("GB-MOV",(7,7)),("GB-MOV",(14,14))])
def test_movement_exact_local_boundaries(name,mats):
    d,r=_ComputeRangesUnderTest(dram()),resolver()
    i=d.add(request(r,name,mats))
    for index,t in enumerate(timeline(name,edges=False)[1]):
        issue(d,i,t)
        if name=="LC-MOV" and index in (1,2,3):
            assert d.state(i)["phase"]=="MovementDataValid"
    assert d.state(i)["phase"]=="Recovering"

def test_source_dependency_not_latest_destination():
    d,r=_ComputeRangesUnderTest(dram()),resolver()
    i=d.add(request(r,"GB-MOV"))
    issue(d,i,0)
    issue(d,i,30,boundary=False)
    issue(d,i,90+3-2)  # Source occurrence 0; independent of destination at 30.
    issue(d,i,30+90+3-2)
    issue(d,i,121+66+2-1)

def test_column_bus_occupancy_and_independent_row_bus():
    d,r=_ComputeRangesUnderTest(dram()),resolver()
    d.raw("ACT",[0,1,0,0,0,0,0],0,issue=True)
    i=d.add(request(r,"LC-MOV"))
    issue(d,i,3)
    issue(d,i,66)
    # Internal column resource blocks other PCs too, without external-DQ history.
    assert not d.raw("RD",[0,1,0,0,0,0,0],67)
    assert d.raw("RD",[0,1,0,0,0,0,0],68)
    assert d.raw("ACT",[0,1,0,0,1,0,0],66,issue=True)

@pytest.mark.parametrize("change",["pc","sid","bg","bank","subarray","reverse","wrap","range"])
@pytest.mark.parametrize("name",["LC-MOV","GB-MOV"])
def test_reject_illegal_movement(change,name):
    d=system()
    a=dict(kind="group",row=[0,0,0,0,0,10],range=[0,0],group=3)
    b=dict(kind="group",row=[0,0,0,0,0,11],range=[1,1] if name=="GB-MOV" else [0,0],group=4)
    if change in ("pc","sid","bg","bank"): b["row"][("pc","sid","bg","bank").index(change)+1]=1
    elif change=="subarray": b["row"][-1]=522
    elif change=="reverse": a["range"],b["range"]=[1,1],[0,0]
    elif change=="wrap": a["range"],b["range"]=[15,15],[0,0]
    elif change=="range": b["range"]=[0,1]
    with pytest.raises((RuntimeError,ValueError)):
        d.submit(d.request(REQUEST_TYPE_IDS[name],[a,b],-1),0)
