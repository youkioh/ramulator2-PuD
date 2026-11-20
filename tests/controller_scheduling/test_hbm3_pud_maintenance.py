"""Accepted Open/AllBank evaluation; injected RFM is structural safety only."""
import pytest
from tests.hbm3_pud import system,request,timeline,COMMANDS,events,times
MAINTENANCE=["PREpb","PREab","REFpb","REFab","RFMpb","RFMab"]

def address(command,pc=0,sid=0,bank=0):
    return [0,pc,-1,-1,-1,-1,-1] if command.endswith("ab") else [0,pc,sid,0,bank,0,0]

@pytest.mark.parametrize("name",COMMANDS)
@pytest.mark.parametrize("command",MAINTENANCE)
@pytest.mark.parametrize("phase",["active","recovering"])
def test_protection_through_terminal_recovery(name,command,phase):
    d=system()
    assert d.submit(request(d,name,sid=1),0)
    done=timeline(name)[2]
    d.advance(5 if phase=="active" else done-10)
    a=address(command,sid=1)
    assert not d.ready(command,a)
    assert d.priority(command,a)
    d.advance(done-1)
    assert not d.ready(command,a)
    assert len(d.issued())==len(COMMANDS[name]) and not d.completions()
    legal=done if command.startswith("PRE") else done+int(done%2==0)
    d.advance(legal)
    assert d.issued()[-1]["command"]==command and d.issued()[-1]["clk"]==legal
    assert len(d.completions())==1 and d.scheduling()["held"]==0

@pytest.mark.parametrize("command",MAINTENANCE)
def test_pre_first_act_reservation(command):
    d=system()
    assert d.submit(request(d,"NOT"),0)
    assert d.submit(request(d,"NOT",mats=(1,1),sid=1),1)
    d.advance(1)
    assert d.scheduling()["held"]==2 and times(d,1)==[]
    a=address(command,sid=1)
    assert not d.ready(command,a) and d.priority(command,a)
    done=timeline("NOT")[2]+4  # Shared row bus: next rising ACT at 5.
    d.advance(done-1)
    assert not d.ready(command,a)
    d.advance(done)
    assert d.issued()[-1]["command"]==command and d.issued()[-1]["clk"]==done
    assert len(d.completions())==2

@pytest.mark.parametrize("name",["NOT","LC-MOV","GB-MOV"])
@pytest.mark.parametrize("command",MAINTENANCE)
@pytest.mark.parametrize("relation",["pc","sid","bank"])
def test_real_pc_and_bank_maintenance_scopes(name,command,relation):
    d=system()
    assert d.submit(request(d,name),0)
    d.advance(10)
    a=address(command,pc=int(relation=="pc"),sid=int(relation=="sid"),bank=int(relation=="bank"))
    assert d.priority(command,a)
    d.advance(11)
    blocked=command.endswith("ab") and relation!="pc"
    assert (d.issued()[-1]["command"]==command)==(not blocked)
    d.advance(1500)
    assert len(d.completions())==1 and d.scheduling()["held"]==0

def test_allbank_evaluation_zero_rfm():
    d=system(refresh="AllBank")
    for i,name in enumerate(COMMANDS):
        assert d.submit(request(d,name,pc=i%2,sid=(i//2)%2,bank=i//4),i)
    d.advance(26000)
    assert len(d.completions())==7
    refresh=[e for e in d.issued() if e["command"].startswith("REF")]
    assert refresh and all(e["command"]=="REFab" for e in refresh)
    assert {e["addr_vec"][1] for e in refresh}=={0,1}
    assert all(e["addr_vec"][2:]==[-1]*5 for e in refresh)
    assert not any(e["command"].startswith("RFM") for e in d.issued())

@pytest.mark.parametrize("name",["NOT","LC-MOV","GB-MOV"])
@pytest.mark.parametrize("access",["ACT","RD","WR","RDA","WRA"])
def test_conventional_act_access_ap_and_pre(name,access):
    d=system()
    a=address("ACT")
    assert d.priority("ACT",a)
    d.advance(100)
    if access!="ACT":
        assert d.priority(access,a)
        d.advance(101)
    assert d.submit(request(d,name),0)
    d.advance(1000)
    if access in ("RDA","WRA"):
        nominal=70 if access=="RDA" else 142
        first_legal=101+nominal+2-3
        expected=first_legal+int(first_legal%2==0)
    else:
        pre=next(e["clk"] for e in events(d,0) if e["command"]=="PREpb")
        assert pre=={"ACT":101,"RD":120,"WR":192}[access]
        first_legal=pre+52+1-3
        expected=first_legal+int(first_legal%2==0)
    first=next(e["clk"] for e in events(d,0) if e["command"] in ("ACT_PUD_S_OC","ACT_MOV"))
    assert first==expected and len(d.completions())==1

def test_promotion_pressure_and_priority_do_not_strand_movement():
    # Structural stress only: lengthen restoration so 70 movements acquire
    # ownership before any retire, exceeding the real 64-entry active buffer.
    # Evaluation uses the unmodified Accepted baseline in the separate test.
    import ramulator
    from ramulator._ramulator_test import _LocatedSystemUnderTest
    from tests.hbm3_pud import controller_config,resolver
    cfg=controller_config(pud_buffer_size=80)
    cfg["dram"]=ramulator.dram.HBM3_PuD(
        org_preset="HBM3_8Gb_8hi",timing_preset="HBM3_6400Mbps",nRAS=1000).to_config()
    d=_LocatedSystemUnderTest(cfg,resolver(cfg["dram"]),install=False)
    for i in range(70):
        # Test observer has 64 sources; source reuse is legal for distinct Requests.
        assert d.submit(request(d,"LC-MOV",mats=(i%16,i%16),bank=(i//16)%4,bg=i//64),i%64)
    d.advance(285)
    assert d.scheduling()["held"]==70 and d.scheduling()["active_size"]==64
    assert d.priority("REFab",address("REFab"))
    d.advance(10000)
    assert len(d.completions())==70 and d.scheduling()["held"]==0
    refresh=next(e for e in d.issued() if e["command"]=="REFab")
    assert refresh["clk"]>=max(e["depart"] for e in d.completions())

def test_ordinary_stream_matches_conventional_hbm3():
    import ramulator
    from ramulator._ramulator_test import _LocatedSystemUnderTest
    from tests.hbm3_pud import controller_config,resolver
    streams=[]
    for pud in (False,True):
        cfg=controller_config()
        if not pud:
            cfg["dram"]=ramulator.dram.HBM3(
                org_preset="HBM3_8Gb_8hi",timing_preset="HBM3_6400Mbps").to_config()
            cfg.pop("pud_placement_profile")
        d=_LocatedSystemUnderTest(cfg,resolver(cfg["dram"]),install=False)
        for i,a in enumerate([0,1024,2048,4096,16384,65536]):
            assert d.submit_ordinary(a,0,i)
        d.advance(1000)
        assert len(d.completions())==6 and d.tick_duration_ns==0.3125
        streams.append((d.issued(),d.completions(),d.stats()["controller"]["read_throughput_MBps"]))
    assert streams[0]==streams[1]
