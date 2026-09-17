import itertools
import pytest
from tests.hbm3_pud import system,request,timeline,COMMANDS,events,times

@pytest.mark.parametrize("scheduler",["FRFCFS","FRFCFS-RowHit"])
@pytest.mark.parametrize("name",COMMANDS)
@pytest.mark.parametrize("mats",[(0,0),(7,7),(14,14)])
def test_public_primitive_exact_timeline_completion(scheduler,name,mats):
    d=system(scheduler)
    assert d.submit(request(d,name,mats),0)
    commands,clocks,done=timeline(name)
    d.advance(done-1)
    assert d.completions()==[] and d.scheduling()["held"]==1
    assert times(d,0)==clocks
    assert [e["command"] for e in events(d,0)]==commands
    d.advance(done)
    assert d.completions()[0]["depart"]==done and d.scheduling()["held"]==0
    d.advance(done+100)
    assert len(d.completions())==1

@pytest.mark.parametrize("destinations",[1,2,5,32])
def test_rowcopy_destinations(destinations):
    d=system()
    assert d.submit(request(d,destinations=destinations),0)
    commands,clocks,done=timeline("RowCopy",destinations)
    d.advance(done)
    assert times(d,0)==clocks
    assert len(d.completions())==1

@pytest.mark.parametrize("scheduler",["FRFCFS","FRFCFS-RowHit"])
@pytest.mark.parametrize("first,second",list(itertools.product(COMMANDS,repeat=2)))
@pytest.mark.parametrize("relation",["disjoint","intersect","bank","pc","sid","no_salp"])
def test_ordered_footprint_pairs(scheduler,first,second,relation):
    d=system(scheduler)
    assert d.submit(request(d,first),0)
    assert d.submit(request(d,second,mats=(4,4) if relation in ("disjoint","no_salp") else (0,0),
        bank=int(relation=="bank"),pc=int(relation=="pc"),sid=int(relation=="sid"),
        row=522 if relation=="no_salp" else 40),1)
    d.advance(1500)
    assert len(d.completions())==2 and d.scheduling()["held"]==0
    done={c["source_id"]:c["depart"] for c in d.completions()}
    starts=[times(d,i)[0] for i in range(2)]
    for i,name in enumerate((first,second)):
        assert [e["command"] for e in events(d,i)]==COMMANDS[name]
        assert done[i]==times(d,i)[-1]+52
    if relation in ("intersect","no_salp"):
        leader=starts.index(min(starts))
        assert starts[1-leader]>=done[leader]
    else: assert max(starts)<min(done.values())

@pytest.mark.parametrize("relation",["mats","banks"])
def test_more_than_eight_disjoint_requests(relation):
    d=system()
    for i in range(12):
        assert d.submit(request(d,"NOT",mats=(i,i) if relation=="mats" else (0,0),
            bank=i%4 if relation=="banks" else 0,bg=i//4 if relation=="banks" else 0),i)
    d.advance(1)
    assert d.scheduling()["held"]==12
    d.advance(45)
    assert [times(d,i) for i in range(12)]==[[1+4*i] for i in range(12)]
    assert d.completions()==[]
    d.advance(600)
    assert len(d.completions())==12 and d.scheduling()["held"]==0

def test_legal_row_and_column_same_tick():
    d=system()
    assert d.submit(request(d,"LC-MOV"),0)
    d.advance(64)
    assert d.submit(request(d,"NOT",pc=1),1)
    d.advance(65)
    assert [(e["command"],e["clk"]) for e in d.issued()[-2:]]==[("RD_MOV",65),("ACT_PUD_S_OC",65)]

@pytest.mark.parametrize("role,name,start",[
    ("ACT_PUD_S_OC","NOT",303),("ACT_PUD_OC","MAJ3",303),
    ("ACT_PUD","RowCopy",197),("ACT_PUD_S","MAJ3",259),
    ("ACT_MOV","LC-MOV",303),("N","NOT",197)])
@pytest.mark.parametrize("relation",["same","bank","sid","pc"])
def test_real_pud_falling_pre_pairing(role,name,start,relation):
    d=system()
    assert d.submit(request(d,"LC-MOV"),0)  # Independent nominal terminal PRE at 306.
    d.advance(start-1)
    assert d.submit(request(d,name,mats=(4,4),bank=int(relation=="bank"),
        sid=int(relation=="sid"),pc=int(relation=="pc")),1)
    d.advance(310)
    target=305 if role=="N" else 303
    assert any(e["command"]==role and e["clk"]==target for e in events(d,1))
    assert times(d,0)[-1]==(307 if relation=="same" else 306)
    # Same-PC different Sid is a different Bank for pairing.
    assert all(e["clk"]%2 for e in d.issued() if e["command"]!="PREpb")

@pytest.mark.parametrize("name",COMMANDS)
def test_reentrant_callback_after_release(name):
    d=system()
    accepted=[]
    def callback(done):
        assert done["held"]==0
        accepted.append(d.submit(request(d,name),1))
    assert d.submit(request(d,name),0,callback)
    done=timeline(name)[2]
    d.advance(done-1)
    assert accepted==[]
    d.advance(done)
    assert accepted==[True]
    d.advance(1500)
    assert len(d.completions())==2 and d.scheduling()["held"]==0
    assert times(d,1)[0]==done+int(done%2==0)

def test_queue_backpressure_retries_and_exact_once():
    d=system()
    pending=list(range(60))
    accepted=[]
    retries=0
    for tick in range(1,4001):
        while pending:
            source=pending[0]
            # Four PCs/Sids and four Banks: 16 independent physical Banks.
            if not d.submit(request(d,"NOT",pc=(source//8)%2,sid=(source//4)%2,bank=source%4),source):
                retries+=1
                break
            accepted.append(pending.pop(0))
        d.advance(tick)
        if len(d.completions())==60: break
    assert retries>0 and not pending and accepted==list(range(60))
    assert len({c["source_id"] for c in d.completions()})==60
    assert d.scheduling()["held"]==0

def test_analytic_movement_schedules():
    assert timeline("LC-MOV")[1:]==([1,65,93,143,235,306],358)
    assert timeline("GB-MOV")[1:]==([1,5,93,97,164],216)

def test_runtime_duration_and_throughput():
    d=system()
    assert d.tick_duration_ns==0.3125
    assert d.submit_ordinary(0,0,0)
    d.advance(200)
    stats=d.stats()["controller"]
    assert stats["num_read_reqs_served"]==1
    assert stats["read_throughput_MBps"]==32*1e6/(200*312.5)

@pytest.mark.parametrize("name",["RowCopy","MAJ3","MAJ5","NOT","NOT_COPY","LC-MOV"])
@pytest.mark.parametrize("mats",[(7,8),(0,15)])
def test_range_width_does_not_change_isolated_timing(name,mats):
    d=system()
    assert d.submit(request(d,name,mats),0)
    commands,clocks,done=timeline(name)
    d.advance(done)
    assert times(d,0)==clocks and len(d.completions())==1
