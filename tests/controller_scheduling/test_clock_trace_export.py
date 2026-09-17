"""Exact duration transport through real recorders and the viewer's readers."""
import json
import shutil
import struct
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import ramulator
from tests.controller_scheduling.harness import ControllerUnderTest
from tests.controller_scheduling.GenericDDRController.test_movement_trace_visibility import (
    live_trace_server, read_cstr,
)

ROOT = Path(__file__).resolve().parents[2]
CASES = [
    ("HBM3", "HBM3_8Gb_8hi", "HBM3_6400Mbps", "make_hbm34", 312.5),
    ("HBM3_PuD", "HBM3_8Gb_8hi", "HBM3_6400Mbps", "make_hbm34", 312.5),
    ("HBM4", "HBM4_32Gb_8Hi", "HBM4_8000Mbps", "make_hbm34", 250),
    ("DDR4", "DDR4_8Gb_x8", "DDR4_2400R", "make_generic_ddr", 833),
    ("GDDR7", "GDDR7_16Gb_x8", "GDDR7_28000_PAM3", "make_gddr7", 571),
]

def record(case, plugin):
    standard, org, timing, factory, duration = case
    dram = getattr(ramulator.dram, standard)(org_preset=org, timing_preset=timing)
    if standard == "HBM3_PuD":
        # Direct physical Requests: external hierarchy conversion is deferred G5.
        from tests.hbm3_pud import system, request
        dut = system(controller_plugins=[plugin.to_config()])
        assert dut.submit(request(dut, "RowCopy"), 0)
        dut.advance(400)
        dut.finalize()
        return SimpleNamespace(timings=dict(zip(dram.timing_params,dram.to_config()["timing"])),
                               history=[SimpleNamespace(**e) for e in dut.issued()])
    dut = getattr(ControllerUnderTest, factory)(dram, controller_plugins=[plugin])
    dut.send_request("Read", [0] * len(dut.level_names))
    dut.run_until_idle(max_ticks=512)
    dut.stats()
    return dut

def run_node(script, *args):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node 22+ is required to exercise the actual TypeScript viewer")
    return json.loads(subprocess.check_output(
        [node, "--no-warnings", "--input-type=module", "-e", script, *map(str,args)],
        text=True, cwd=ROOT))

@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_binary_and_viewer_preserve_duration(tmp_path, case):
    dut = record(case, ramulator.controller_plugin.BinTraceRecorder(
        path=str(tmp_path/"trace"), dram_type=case[0]))
    path = tmp_path/"trace.ch0.ram2bin"
    data = path.read_bytes()
    duration = case[-1]
    assert tuple(data[8:10]) == (1, 2 if duration % 1 else 1)
    levels, commands, timings = struct.unpack_from("<HHH", data, 12)
    offset = 64
    for _ in range(levels):
        _, offset = read_cstr(data, offset)
    offset += 4 * levels
    for _ in range(commands):
        _, offset = read_cstr(data, offset)
    offset += 2 * commands
    names = []
    for _ in range(timings):
        name, offset = read_cstr(data, offset)
        names.append(name)
    values = struct.unpack_from("<" + ("d" if duration % 1 else "i") * timings, data, offset)
    assert dict(zip(names, values)) == dut.timings
    # Exercise the actual TypeScript binary reader, including event alignment.
    result = run_node("""
        import {readFileSync} from 'node:fs';
        import {parseTrace} from './visualizer/app/composables/useTrace.ts';
        const raw=readFileSync(process.argv[1]);
        const trace=parseTrace(raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.byteLength));
        console.log(JSON.stringify({duration:trace.spec.timingValues[trace.spec.timingNames.indexOf('tCK_ps')],
          clocks:Array.from(trace.arrays.clk,Number)}));
    """, path)
    assert result["duration"] == duration
    assert result["clocks"] == [e.clk for e in dut.history]

@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_live_and_viewer_preserve_duration(tmp_path, case):
    with live_trace_server() as (port, messages):
        dut = record(case, ramulator.controller_plugin.LiveTraceStreamer(
            port=port, tick_interval=100000, update_interval_s=3600, dram_type=case[0]))
    init = next(m for m in messages if m["type"] == "init")
    assert dict(zip(init["spec"]["timingNames"],init["spec"]["timingValues"])) == dut.timings
    fixture = tmp_path/"init.json"
    fixture.write_text(json.dumps(init))
    # Compile the real live module, replacing only its unused application-store
    # import; invoke its internal builder with the real recorder's init message.
    result = run_node("""
        import {readFileSync} from 'node:fs';
        import {stripTypeScriptTypes} from 'node:module';
        let source=stripTypeScriptTypes(readFileSync('visualizer/app/composables/useStreamSession.ts','utf8'));
        source=source.replace("import { useSessionStore } from '~/stores/session';",'');
        source+='; export { _resetBuffers, _buildTrace };';
        const live=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
        const init=JSON.parse(readFileSync(process.argv[1],'utf8'));
        live._resetBuffers(init.header.levelCount);
        const trace=live._buildTrace(init.header,init.spec);
        console.log(JSON.stringify(trace.spec.timingValues[trace.spec.timingNames.indexOf('tCK_ps')]));
    """, fixture)
    assert result == case[-1]

def test_viewer_setup_preserves_duration_and_integer_scheduling():
    result = run_node("""
        import {readFileSync} from 'node:fs';
        import {stripTypeScriptTypes} from 'node:module';
        const vue=readFileSync('visualizer/app/pages/trace/setup.vue','utf8');
        const source=stripTypeScriptTypes(vue.split('<script setup lang="ts">')[1].split('</script>')[0]);
        const toInt=source.slice(source.indexOf('function toInt('),source.indexOf('function resetValues('));
        const apply=source.slice(source.indexOf('function applyOverrides('),source.indexOf('async function continueToTrace('));
        const trace={spec:{},header:{}};
        const pendingTrace={value:trace}, readLatency={value:12.9};
        const timingRows=[{name:'tCK_ps',value:312.5},{name:'nRCD',value:62.9}];
        console.log(JSON.stringify(new Function('pendingTrace','readLatency','timingRows',
            toInt+apply+'return applyOverrides();')(pendingTrace,readLatency,timingRows).values));
    """)
    assert result == [312.5, 62]
