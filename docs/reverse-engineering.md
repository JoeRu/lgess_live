# LG ESS ED05K000E00 — where the live values are, and how they were found

As of 2026-10-19.

## Goal

The LG ESS (hybrid battery inverter) writes measurements to `/nvdata/DBFiles/ems_DEU.db` only
every 15 minutes, and tools that read that database inherit the delay. Smart charging (evcc)
needs power values at second resolution. The question was whether such values exist on the
device and how to read them.

**Result: yes.** The values are in shared memory, updated every second. `lgess_live` serves
them at `http://<ess-ip>:8085/api/live`.

## System

| | |
|---|---|
| Hostname | `lge-ems` (Avahi: `lge-ems-5.local`) |
| Kernel | Linux 3.10.17, armv7l (i.MX6), BusyBox 1.21.1 |
| Access | root over SSH |
| Open ports (before) | 22 (ssh), 111 (rpcbind). No web or API port |
| Python | 2.7.3, incomplete: **no** `ctypes`, `json`, `BaseHTTPServer`, `SocketServer`. `site` is broken, so only `python -S` works |
| Root FS | ext3, writable (`/dev/mmcblk0p3`) |
| Init | SysV, runlevel 5 (`/etc/rc5.d`) |
| Battery | defective and disconnected on the development unit, so all `batt_*` values are 0 |

### Processes

| Process | Role |
|---|---|
| `PCSMgr` | talks to the inverter DSP (PCS) |
| `PowerMeterMgr` | grid meter over Modbus (`libmodbus`) |
| `ALGMgr` | control algorithm (charge/discharge/feed-in), sends commands to PCSMgr |
| `DBMgr` | writes quarter-hour/day/week/month values to SQLite |
| `reportmgr` | upload to the LG cloud (EnerVu), also 15-minute values (`PMSInfo::Set15MinPowerData`) |
| `uxmgr` | touch-display UI |
| `ProcMonMgr` | watchdog for the manager processes |

## Communication paths

### D-Bus (control only)

Recorded passively with `dbus-monitor --system`. D-Bus carries control commands, no measurements:

- `ems.signal.alomgr` / `alomgr_to_pcs`: ALGMgr → PCS, JSON `{"cmds":[{"start":"45000","data":[...,"<counter>"]}]}`
  (register block 45000, every second with an incrementing heartbeat)
- `ems.signal.pcsmgr` / `pcs`: replies `{"evt":"write_success"}`, `{"evt":"warn_continue"}`

### SysV shared memory (measurements)

`libclipcomm_system.so` provides the class `clipShmem(key, size)`. Locking uses POSIX semaphores
`/dev/shm/sem.clipShMemLock-<key>`. All segments are mode 0666. The key/size mapping comes from the
`clipShmem::clipShmem(unsigned, unsigned)` calls in ALGMgr, DBMgr and reportmgr:

| Key | Size | Created by | Content |
|---|---|---|---|
| **1719** | 743 | PowerMeterMgr | **FromPCS**: live inverter and meter values (packed struct) |
| 1205 | 213 | ALGMgr | **DBAccum**: running 15-minute accumulators (W·s) plus the last quarter's values |
| 1605 | 9364 | ALGMgr | ring buffer of per-second samples (52-byte records incl. Unix time and frequency) |
| 1604 | 12244 | ProcMonMgr | process monitoring (heartbeat counters) |
| 1208 | 158 | uxmgr | AlgWrite / UX context |
| 1702 | 522 | PCSMgr | ToPCS (commands to the inverter) |
| 1206 | 160 | netmgr | network status (time counters) |
| 1207, 1309, 1602, 1603 | – | – | configuration and status (static) |

## Reverse engineering FromPCS (key 1719)

The binaries are stripped but export their C++ symbols dynamically, which made the analysis direct.

1. `AlgMgrShm` keeps the SHM pointers as members: `GetToPCS()` → `this+48`, **`GetFromPCS()` → `this+52`**,
   `GetAlgWrite()` → `this+56`, `GetNVRAM()` → `this+60`, `GetDBAccum()` → `this+64`.
2. `AlgMgrShm::GetLogPCSInformation()` (ALGMgr @ `0x24bf4`) first assigns 17 label strings, then formats
   one value from `FromPCS` per label with `sprintf`. `ldr r2, [r3, #off]` gives the offset;
   `vcvt.f64.f32` or the format string (`%.3f` vs. `%5d`) gives the type.
3. Cross-check against a memory dump: offset 331 as float = 50.05 Hz, so FromPCS is key 1719.

| Label (from ALGMgr) | Offset | Type | Format |
|---|---|---|---|
| Meter Power | 327 | float | `%.3f W` |
| Meter Freq | 331 | float | `%.3f Hz` |
| AC Power | 149 | int32 | `%5d W` |
| AC Freq | 195 | float | `%.3f Hz` |
| PV Power | AlgWrite+57 | uint16 | `%5d W` |
| BATT Power | 141 | int32 | `%5d W` |
| BATT Voltage | 125 | float | `%.3f V` |
| BATT SOC | 219 | float | `%.3f %%` |
| DC Link Voltage | 157 | int32 | `%5d V` |
| PV1 Current | 165 | int32 | `%5d A` |
| PV1 Voltage | 169 | int32 | `%5d V` |
| PV1 Power | 173 | int32 | `%5d W` |
| PV2 Current | 177 | int32 | `%5d A` |
| PV2 Voltage | 181 | int32 | `%5d V` |
| PV2 Power | 185 | int32 | `%5d W` |
| BAT Current | 129 | float | `%.3f A` |
| BAT Status | 203 | int32 | `%5d` |

The struct is packed, so the offsets are not 4-byte aligned. All values are little endian.

### Plausibility check

Live values against the database quarter-hour value (16:15, `tbl_record_quarter`):

| | Live (SHM 1719) | DB quarter |
|---|---|---|
| PV | 1303 + 1027 = 2330 W DC, AC 2146 W | `pv_power` 2216 |
| Grid | meter −1332 W | `grid_feed_in` 1339, `grid_power_purchase` 0 |
| Consumption | AC + meter = 814 W | `load_power` 876 |

So **meter power is positive on import and negative on export**, the evcc convention.
House consumption = AC power + meter power.

Further observations:
- Segment 1205 holds the last quarter's values (offset 84 = 2216 `pv_power`, 168 = 1339 `grid_feed_in`,
  124 = 876 `load_power`) and the quarter timestamp (offset 68). DBMgr fills the database from it.
- `reportmgr` builds the cloud JSON (`currentInfo`: `pvP`, `loadP`, `gridP`, `battChg`, …) in
  `CommReportServer::testRepotPowerBody3` from a struct of `std::string` fields, also from 15-minute data.
- Not verified: the sign of `BATT Power` (charge vs. discharge), because the battery is disconnected.

## The `lgess_live` service

- `lgess_live.py` (Python 2.7, `python -S`, only `os`, `socket`, `struct`, `thread`, `time`); one thread per
  connection since 2026-11-01.
- Finds a process that has `/SYSV000006b7` mapped via `/proc/*/maps` and reads the segment through
  `/proc/<pid>/mem`. Without `ctypes` there is no access to the lock semaphore, so it reads twice until both
  reads match. If an LG process restarts, the mapping is looked up again automatically.
- The LG processes are only read, never modified. The service uses about 4 MB RAM and caches values for 1 s.
- HTTP on port **8085**: `GET /api/live` (also `/` and `/live`) returns JSON, other paths 404, read errors 503.

Derived fields: `pv_power_w = pv1 + pv2` (DC), `grid_power_w = meter_power_w`,
`grid_import_w` and `grid_export_w` (each ≥ 0), `load_power_w = ac_power_w + meter_power_w`.

### Files on the device

| Path | |
|---|---|
| `/usr/local/lgess_live/lgess_live.py` | service |
| `/etc/init.d/lgess_live` | init script (`start`, `stop`, `restart`, via `start-stop-daemon`) |
| `/etc/rc5.d/S95lgess_live` | autostart |
| `/var/run/lgess_live.pid` | PID file |

An LG firmware update could overwrite these files or change the struct offsets. In that case, derive the
offsets again from `GetLogPCSInformation` as described above.

## Open points

- Check the sign of `batt_power_w` once a battery is connected again.
- Optional: MQTT push instead of HTTP pull (no library on the device; the protocol would have to be written by hand on `socket`).
- Optional: fully decode ring buffer 1605 and DBAccum 1205 (per-second history, running quarter-hour energy).

## Analysis artifacts

Not part of this repository: the ARM disassembly and helper scripts used for the analysis, and copies of
LG's binaries, libraries and memory dumps from the device (LG's property).
