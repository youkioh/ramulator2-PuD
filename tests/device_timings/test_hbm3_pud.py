import pytest
from ramulator._ramulator_test import _ComputeRangesUnderTest
from tests.hbm3_pud import dram,resolver,request,timeline,COMMANDS,PHASE
from tests.device_timings.test_pud_compute_ranges import issue

@pytest.mark.parametrize("name",list(COMMANDS)[:5])
@pytest.mark.parametrize("mats",[(0,0),(7,8),(0,15)])
def test_compute_nominal_reception_boundaries(name,mats):
    d,r=_ComputeRangesUnderTest(dram()),resolver()
    i=d.add(request(r,name,mats))
    for t in timeline(name,edges=False)[1]: issue(d,i,t)
    assert d.state(i)["phase"]=="Recovering"

@pytest.mark.parametrize("destinations",[1,2,5,32])
def test_rowcopy_destinations(destinations):
    d,r=_ComputeRangesUnderTest(dram()),resolver()
    i=d.add(request(r,destinations=destinations))
    for t in timeline("RowCopy",destinations,edges=False)[1]: issue(d,i,t)

@pytest.mark.parametrize("name",["NOT","MAJ3","LC-MOV"])
@pytest.mark.parametrize("previous,nominal",[
    ("PREpb",52),("PREab",52),("REFab",832),("RFMab",832),
    ("REFpb",640),("RFMpb",640)])
@pytest.mark.parametrize("relation",["same","bank","sid","pc"])
def test_incoming_recovery(name,previous,nominal,relation):
    d,r=_ComputeRangesUnderTest(dram()),resolver()
    a=[0,0,-1,-1,-1,-1,-1] if previous.endswith("ab") else [0,0,0,0,0,0,0]
    d.raw(previous,a,0,issue=True)
    i=d.add(request(r,name,bank=int(relation=="bank"),sid=int(relation=="sid"),pc=int(relation=="pc")))
    if relation=="same" or (previous.endswith("ab") and relation!="pc"): ready=nominal+1-3
    elif previous in ("REFpb","RFMpb") and relation!="pc": ready=26+1-3
    else: ready=1
    issue(d,i,ready)

@pytest.mark.parametrize("ap,at,nominal",[("RDA",63,70),("WRA",31,142),("RDA",200,70),("WRA",200,142)])
@pytest.mark.parametrize("name",["NOT","MAJ3","LC-MOV"])
def test_act_nrc_survives_early_ap(name,ap,at,nominal):
    d,r=_ComputeRangesUnderTest(dram()),resolver()
    a=[0,0,0,0,0,0,0]
    d.raw("ACT",a,0,issue=True)
    d.raw(ap,a,at,issue=True)
    i=d.add(request(r,name))
    issue(d,i,max(144,at+nominal+2-3))

def test_pc_local_pre_publication():
    d,r=_ComputeRangesUnderTest(dram()),resolver()
    i=d.add(request(r))
    for t in timeline("RowCopy",edges=False)[1]: issue(d,i,t)
    terminal=timeline("RowCopy",edges=False)[1][-1]
    same=[0,0,1,0,0,0,0]
    other=[0,1,1,0,0,0,0]
    assert not d.raw("PREpb",same,terminal+3)
    assert d.raw("PREpb",same,terminal+4)
    assert d.raw("PREpb",other,terminal+1)
    assert d.raw("REFpb",same,terminal+1)
    # Closing one mat must not publish PC/Bank nRP to new disjoint openings.
    j=d.add(request(r,"NOT",mats=(2,2)))
    issue(d,j,terminal+1)

def test_exact_half_tick_calibration():
    import ramulator
    spec=ramulator.dram.HBM3_PuD
    t=dict(zip(spec.timing_params,dram()["timing"]))
    assert [t[x] for x in ["nPUD_ACT_OC","nPUD_ACT","nPUD_ACT_S_OC","nPUD_ACT_S","nPUD_N","nRELOC"]] == [29,13,106,90,112,4]
    assert PHASE["N"]*t["tCK_ps"]==35000
