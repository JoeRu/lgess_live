#!/usr/bin/python -S
# -*- coding: utf-8 -*-
"""
lgess_live - live values of an LG ESS (ED05K000E00) over HTTP/JSON.

Reads, read-only, the SysV shared-memory segment 1719 ("FromPCS", 743 bytes,
packed) that the LG manager processes update every second with the inverter
and grid-meter values. Offsets come from the disassembly of
AlgMgrShm::GetLogPCSInformation() in /usr/bin/ALGMgr.

The device has no ctypes, so the segment is read through /proc/<pid>/maps and
/proc/<pid>/mem of a process that has it mapped.

The device's Python 2.7 is incomplete (no json, no BaseHTTPServer, no
SocketServer), hence a minimal socket-based HTTP server and hand-made JSON.

Start:  python -S /usr/local/lgess_live/lgess_live.py [port]   (default 8085)
        python -S lgess_live.py --once                         (print one reading)
"""
import os
import socket
import struct
import sys
import time
import thread

SHM_NAME = "/SYSV000006b7"   # key 1719
SHM_SIZE = 743
CACHE_SEC = 1.0

# (name, offset, struct format) - offsets from GetLogPCSInformation
FIELDS = [
    ("meter_power_w",  327, "f"),   # grid meter, + import / - export
    ("meter_freq_hz",  331, "f"),
    ("ac_power_w",     149, "i"),   # inverter AC output
    ("ac_freq_hz",     195, "f"),
    ("batt_power_w",   141, "i"),
    ("batt_voltage_v", 125, "f"),
    ("batt_current_a", 129, "f"),
    ("batt_soc_pct",   219, "f"),
    ("batt_status",    203, "i"),
    ("dc_link_v",      157, "i"),
    ("pv1_current_a",  165, "i"),
    ("pv1_voltage_v",  169, "i"),
    ("pv1_power_w",    173, "i"),
    ("pv2_current_a",  177, "i"),
    ("pv2_voltage_v",  181, "i"),
    ("pv2_power_w",    185, "i"),
]


def find_mapping():
    """(pid, addr) of a process that has the segment mapped."""
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            for line in open("/proc/%s/maps" % pid):
                if SHM_NAME in line:
                    return pid, int(line.split("-", 1)[0], 16)
        except IOError:
            continue
    raise IOError("shm segment %s not mapped by any process" % SHM_NAME)


_map = [None]


def read_raw():
    for attempt in (0, 1):
        if _map[0] is None:
            _map[0] = find_mapping()
        pid, addr = _map[0]
        try:
            f = open("/proc/%s/mem" % pid, "rb")
            try:
                f.seek(addr)
                a = f.read(SHM_SIZE)
                f.seek(addr)
                b = f.read(SHM_SIZE)
            finally:
                f.close()
            # no access to the clipShMemLock semaphore without ctypes:
            # read twice, and again while the reads differ (write in progress)
            for _ in range(5):
                if a == b:
                    break
                a = b
                f = open("/proc/%s/mem" % pid, "rb")
                f.seek(addr)
                b = f.read(SHM_SIZE)
                f.close()
            return a
        except (IOError, OSError):
            _map[0] = None   # process restarted -> look it up again
    raise IOError("cannot read shm")


def decode(raw):
    v = {}
    for name, off, fmt in FIELDS:
        v[name] = struct.unpack_from("<" + fmt, raw, off)[0]
    pv = v["pv1_power_w"] + v["pv2_power_w"]
    grid = v["meter_power_w"]
    v["pv_power_w"] = pv
    v["grid_power_w"] = grid                       # evcc: + import, - export
    v["grid_import_w"] = max(grid, 0.0)
    v["grid_export_w"] = max(-grid, 0.0)
    v["load_power_w"] = v["ac_power_w"] + grid     # house consumption
    v["timestamp"] = int(time.time())
    return v


def to_json(d):
    parts = []
    for k in sorted(d):
        val = d[k]
        if isinstance(val, float):
            val = "%.3f" % val
        parts.append('"%s": %s' % (k, val))
    return "{" + ", ".join(parts) + "}"


_cache = [0.0, None]


_lock = thread.allocate_lock()   # cache + /proc reads shared by all handler threads


def get_live_json():
    _lock.acquire()
    try:
        now = time.time()
        if _cache[1] is None or now - _cache[0] >= CACHE_SEC:
            _cache[1] = to_json(decode(read_raw()))
            _cache[0] = now
        return _cache[1]
    finally:
        _lock.release()


def respond(conn, status, body, ctype="application/json"):
    conn.sendall("HTTP/1.0 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
                 "Connection: close\r\n\r\n%s" % (status, ctype, len(body), body))


MAX_THREADS = 16
_active = [0]
_active_lock = thread.allocate_lock()


def handle(conn):
    try:
        # Each connection has its own thread (2026-11-01), so a slow client only
        # delays itself. Until then connections were served one after another and
        # a client slow to send its request stalled everyone else.
        conn.settimeout(2)
        req = conn.recv(2048)
        path = req.split(" ", 2)[1] if req.count(" ") >= 2 else "/"
        if path in ("/", "/live", "/api/live"):
            try:
                respond(conn, "200 OK", get_live_json())
            except Exception as e:
                respond(conn, "503 Service Unavailable", '{"error": "%s"}' % str(e).replace('"', "'"))
        else:
            respond(conn, "404 Not Found", '{"error": "not found"}')
    except Exception:
        pass
    finally:
        conn.close()
        _active_lock.acquire()
        _active[0] -= 1
        _active_lock.release()


def serve(port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(16)
    while True:
        conn, _ = srv.accept()
        _active_lock.acquire()
        busy = _active[0] >= MAX_THREADS
        if not busy:
            _active[0] += 1
        _active_lock.release()
        if busy:                       # bound the thread count (scanners, floods)
            conn.close()
            continue
        try:
            thread.start_new_thread(handle, (conn,))
        except Exception:
            _active_lock.acquire()
            _active[0] -= 1
            _active_lock.release()
            conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        print(get_live_json())
    else:
        serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8085)
