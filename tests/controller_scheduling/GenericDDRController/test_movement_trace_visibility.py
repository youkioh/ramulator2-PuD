import csv
import json
import multiprocessing
import queue
import struct
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from ramulator.dram.spec import REQUEST_TYPE_IDS

import ramulator
import tests.controller_scheduling.harness as cs

pytestmark = pytest.mark.controller_scheduling


def make_dram():
    return ramulator.dram.DDR4_PuD_Movement(
        org_preset="DDR4_8Gb_x8",
        timing_preset="DDR4_2400R",
        rank=1,
    )


def operand(dut, *, row, column):
    return dut.addr_vec(
        Rank=0,
        BankGroup=0,
        Bank=0,
        Row=row,
        Column=column,
    )


def run_isolated_movement(plugin, type_name):
    dut = cs.ControllerUnderTest.make_generic_ddr(
        make_dram(),
        controller_plugins=[plugin],
    )
    source = operand(dut, row=10, column=3)
    destination = operand(dut, row=11, column=5)
    mats = (3, 5) if type_name == "LC-MOV" else (3, 4)
    dut.send_movement_request_for_testing(
        type_name,
        [source, destination],
        *mats,
        source_id=7,
    )
    dut.run_until_idle(max_ticks=256)
    dut.stats()  # Finalizes buffered trace plugins before parsing their output.
    return source, destination


def expected_stream(type_name, source, destination):
    if type_name == "LC-MOV":
        commands = ["ACT_MOV", "RD_MOV", "PREpb", "ACT_MOV", "WR_MOV", "PREpb"]
        addresses = [source, source, source, destination, destination, destination]
    else:
        commands = ["ACT_MOV", "ACT_MOV", "RD_MOV", "WR_MOV", "PREpb"]
        addresses = [source, destination, source, destination, destination]
    return commands, addresses


def assert_isolated_stream(records, type_name, source, destination):
    commands, addresses = expected_stream(type_name, source, destination)
    assert [record["command"] for record in records] == commands
    assert [record["addr"] for record in records] == addresses
    assert all(record["type_id"] == REQUEST_TYPE_IDS[type_name] for record in records)
    assert all(record["source_id"] == 7 for record in records)
    assert [record["clk"] for record in records] == sorted(record["clk"] for record in records)


def read_cstr(data, offset):
    end = data.index(0, offset)
    return data[offset:end].decode("ascii"), end + 1


def parse_cmd_trace_binary(path):
    data = path.read_bytes()
    level_count, command_count = struct.unpack_from("<II", data, 0)
    offset = 8
    for _ in range(level_count):
        _, offset = read_cstr(data, offset)
    command_names = []
    for _ in range(command_count):
        name, offset = read_cstr(data, offset)
        command_names.append(name)

    record_format = "<Q" + "i" * (3 + level_count)
    record_size = struct.calcsize(record_format)
    assert (len(data) - offset) % record_size == 0
    records = []
    while offset < len(data):
        values = struct.unpack_from(record_format, data, offset)
        offset += record_size
        records.append(
            {
                "clk": values[0],
                "command": command_names[values[1]],
                "type_id": values[2],
                "source_id": values[3],
                "addr": list(values[4:]),
            }
        )
    return records


def parse_ram2bin(path):
    data = path.read_bytes()
    assert data[:8] == b"RAM2BIN\0"
    assert tuple(data[8:10]) == (1, 1)
    level_count = struct.unpack_from("<H", data, 12)[0]
    command_count = struct.unpack_from("<H", data, 14)[0]
    num_entries = struct.unpack_from("<Q", data, 32)[0]
    data_offset = struct.unpack_from("<Q", data, 40)[0]

    offset = 64
    for _ in range(level_count):
        _, offset = read_cstr(data, offset)
    offset += 4 * level_count
    command_names = []
    for _ in range(command_count):
        name, offset = read_cstr(data, offset)
        command_names.append(name)

    # RAM2BIN v1.1 has exactly the existing 20 + 4L bytes per event.
    assert len(data) == data_offset + num_entries * (20 + 4 * level_count)

    records = []
    for index in range(num_entries):
        records.append(
            {
                "clk": struct.unpack_from("<q", data, data_offset + 8 * index)[0],
                "arrive": struct.unpack_from("<q", data, data_offset + 8 * num_entries + 8 * index)[
                    0
                ],
                "command": command_names[data[data_offset + 16 * num_entries + index]],
                "type_id": struct.unpack_from("<b", data, data_offset + 17 * num_entries + index)[
                    0
                ],
                "source_id": struct.unpack_from(
                    "<h", data, data_offset + 18 * num_entries + 2 * index
                )[0],
                "addr": [
                    struct.unpack_from(
                        "<i",
                        data,
                        data_offset + (20 + 4 * level) * num_entries + 4 * index,
                    )[0]
                    for level in range(level_count)
                ],
            }
        )
    return records


@pytest.mark.parametrize("type_name", ["LC-MOV", "GB-MOV"])
@pytest.mark.parametrize("binary", [False, True], ids=["csv", "legacy-binary"])
def test_cmd_trace_recorder_exposes_isolated_movement_stream(tmp_path, type_name, binary):
    base = tmp_path / "commands"
    source, destination = run_isolated_movement(
        ramulator.controller_plugin.CmdTraceRecorder(path=str(base), binary=binary),
        type_name,
    )
    path = tmp_path / "commands.ch0"

    if binary:
        records = parse_cmd_trace_binary(path)
    else:
        with path.open(newline="") as trace_file:
            rows = list(csv.DictReader(trace_file))
        records = [
            {
                "clk": int(row["clock"]),
                "command": row["command"],
                "type_id": int(row["type"]),
                "source_id": int(row["source"]),
                "addr": [
                    int(row[level])
                    for level in ("Channel", "Rank", "BankGroup", "Bank", "Row", "Column")
                ],
            }
            for row in rows
        ]

    assert_isolated_stream(records, type_name, source, destination)


@pytest.mark.parametrize("type_name", ["LC-MOV", "GB-MOV"])
def test_bin_trace_recorder_exposes_isolated_movement_stream(tmp_path, type_name):
    base = tmp_path / "commands"
    source, destination = run_isolated_movement(
        ramulator.controller_plugin.BinTraceRecorder(path=str(base), dram_type="DDR4_PuD_Movement"),
        type_name,
    )
    records = parse_ram2bin(tmp_path / "commands.ch0.ram2bin")

    assert_isolated_stream(records, type_name, source, destination)
    assert len({record["arrive"] for record in records}) == 1


@contextmanager
def live_trace_server():
    port_queue = multiprocessing.Queue()
    message_queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=serve_live_trace,
        args=(port_queue, message_queue),
    )
    process.start()
    port = port_queue.get(timeout=5)
    messages = []
    try:
        yield port, messages
    finally:
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join()
        while True:
            try:
                messages.append(message_queue.get_nowait())
            except queue.Empty:
                break


def serve_live_trace(port_queue, message_queue):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            message_queue.put(json.loads(self.rfile.read(length)))
            body = b'{"interrupted":false}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port_queue.put(server.server_address[1])
    try:
        # With the long flush intervals used below, setup/finalize emit exactly
        # init, events, and done.
        for _ in range(3):
            server.handle_request()
    finally:
        server.server_close()


@pytest.mark.parametrize("type_name", ["LC-MOV", "GB-MOV"])
def test_live_trace_streamer_exposes_isolated_movement_stream(type_name):
    with live_trace_server() as (port, messages):
        source, destination = run_isolated_movement(
            ramulator.controller_plugin.LiveTraceStreamer(
                port=port,
                tick_interval=100000,
                update_interval_s=3600,
                dram_type="DDR4_PuD_Movement",
            ),
            type_name,
        )

    init = next(message for message in messages if message["type"] == "init")
    events = [
        event for message in messages if message["type"] == "events" for event in message["events"]
    ]
    command_names = init["spec"]["commandNames"]
    records = [
        {
            "clk": event["clk"],
            "arrive": event["arrive"],
            "command": command_names[event["cmdId"]],
            "type_id": event["typeId"],
            "source_id": event["sourceId"],
            "addr": event["addr"],
        }
        for event in events
    ]

    assert all(
        set(event) == {"clk", "arrive", "cmdId", "typeId", "sourceId", "addr"} for event in events
    )
    assert_isolated_stream(records, type_name, source, destination)
    assert len({record["arrive"] for record in records}) == 1
