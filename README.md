# lgess_live — real-time values from an LG ESS inverter over HTTP

`lgess_live` is a tiny HTTP service that runs **on the LG ESS itself** and serves the
inverter's live measurements (updated every second) as JSON:

```
http://<ess-ip>:8085/api/live
```

```json
{"ac_freq_hz": 50.000, "ac_power_w": 1834, "batt_current_a": 0.000, "batt_power_w": 0,
 "batt_soc_pct": 0.000, "batt_status": 0, "batt_voltage_v": 76.200, "dc_link_v": 624,
 "grid_export_w": 1210.400, "grid_import_w": 0.000, "grid_power_w": -1210.400,
 "load_power_w": 623.600, "meter_freq_hz": 50.010, "meter_power_w": -1210.400,
 "pv1_current_a": 3, "pv1_power_w": 1012, "pv1_voltage_v": 342,
 "pv2_current_a": 2, "pv2_power_w": 905, "pv2_voltage_v": 318,
 "pv_power_w": 1917, "timestamp": 1793515177}
```

The stock firmware only writes energy values to its SQLite database every 15 minutes and
offers no local API. Smart-charging (evcc) and live dashboards (Home Assistant) need
second-level power values; this service provides them.

- **Read-only.** It reads a shared-memory segment that the LG processes already publish.
  Nothing on the device is modified, no LG process is touched.
- **No dependencies.** The device ships an incomplete Python 2.7 (no `json`,
  `BaseHTTPServer`, `ctypes`, `SocketServer`), so the server is plain `socket` + `thread`.
- **Parallel.** Every connection is handled in its own thread (max. 16), so one slow
  client never delays the others. Values are cached for a short moment and read under a lock.

## Compatibility

Developed and tested on an **LG ESS ED05K000E00** (i.MX6, Linux 3.10, BusyBox 1.21,
Python 2.7.3). Other LG ESS models with the same software stack (`PCSMgr`, `ALGMgr`,
`libclipcomm_system`) will likely work, but the memory offsets may differ — check the
values against the device display before relying on them.

You need **root SSH access to the ESS**. How to obtain it is out of scope here.

## Fields

| Field | Unit | Meaning |
|---|---|---|
| `pv1_*`, `pv2_*` | A / V / W | DC values of both PV strings |
| `pv_power_w` | W | `pv1_power_w + pv2_power_w` (DC) |
| `ac_power_w` | W | AC output of the inverter |
| `meter_power_w` | W | grid meter: **+ import / − export** |
| `grid_power_w` | W | same as `meter_power_w` (evcc convention) |
| `grid_import_w`, `grid_export_w` | W | the two directions, each ≥ 0 |
| `load_power_w` | W | house consumption = `ac_power_w + meter_power_w` |
| `ac_freq_hz`, `meter_freq_hz` | Hz | grid frequency (inverter / meter) |
| `dc_link_v` | V | DC link voltage |
| `batt_*` | | battery values. **Unverified:** the development unit had its battery disconnected, so the sign of `batt_power_w` is unknown |
| `timestamp` | s | Unix time of the read |

Errors return HTTP `503` with `{"error": "..."}` (e.g. while the LG processes restart),
unknown paths `404`. `/`, `/live` and `/api/live` all return the values.

## Home Assistant (HACS) — recommended

The repository is also a Home Assistant integration. It installs the service on the ESS
for you and creates all sensors, including kWh counters for the energy dashboard — no
command line, no YAML.

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/JoeRu/lgess_live`,
   category **Integration**. Install **LG ESS Live** and restart Home Assistant.
2. *Settings → Devices & services → Add integration → LG ESS Live*.
3. Enter the ESS address. If the service is not on the ESS yet, tick
   **Install service on the ESS now** and give the SSH user (usually `root`) and password
   (leave empty if there is none). The integration copies the service over SSH, starts it
   and checks that it answers.

You get one device *LG ESS* with:

| Entity | |
|---|---|
| PV power, Grid power (+ import / − export), Grid import, Grid export, Consumption, Grid frequency | W / Hz, enabled |
| PV1/PV2 power, voltage, current, DC link voltage, battery values | disabled by default |
| **Grid import energy, Grid export energy, PV energy, Consumption energy** | kWh, `total_increasing`, ready for the energy dashboard |
| Button **Install or update service** | re-installs the bundled service version over SSH (after an integration update or an ESS firmware update) |

The kWh counters integrate the power values (left Riemann sum) and survive restarts; gaps
longer than 60 s (outage) are not integrated. Polling interval: options, default 5 s.

For the energy dashboard use *Grid import energy* (grid consumption), *Grid export energy*
(return to grid) and *PV energy* (solar production).

**SSH:** the host key of the ESS is accepted on first use, and the SSH password is stored in
the config entry like other Home Assistant credentials. Use the button only in a network
you trust.

## Installation without Home Assistant

From any Linux/macOS machine with SSH access to the ESS:

```sh
git clone https://github.com/JoeRu/lgess_live.git
cd lgess_live
./install.sh <ess-ip>
```

`install.sh` copies the service (`custom_components/lgess_live/ess/`) to
`/usr/local/lgess_live/`, installs the SysV init script `/etc/init.d/lgess_live`, links it to
`/etc/rc5.d/S95lgess_live` (autostart), (re)starts it and prints one reading. Re-run it to
update.

```sh
ssh root@<ess-ip> /etc/init.d/lgess_live restart   # restart
curl http://<ess-ip>:8085/api/live                 # test
./uninstall.sh <ess-ip>                             # remove everything
```

Quick test on the device without installing: `python -S lgess_live.py --once`.

## Home Assistant without the integration (YAML)

If you prefer plain YAML, use the [REST integration](https://www.home-assistant.io/integrations/rest/).
The full example is in [`examples/homeassistant/lgess_live.yaml`](examples/homeassistant/lgess_live.yaml);
put it into a [package](https://www.home-assistant.io/docs/configuration/packages/)
(`packages/lgess_live.yaml`) or under `rest:` in `configuration.yaml`, replace `<ess-ip>`,
then restart Home Assistant.

For the energy dashboard, create one *Integral* helper per power sensor: *Settings →
Devices & services → Helpers → Create helper → Integral sensor*, method **Left**, metric
prefix **k**, time unit **hours**, and use the integrals of *ESS grid import*, *ESS grid
export* and *ESS PV power*. Use `ac_power_w` for solar production if no battery is
connected; `pv_power_w` is the DC side before conversion losses.

## evcc

```yaml
meters:
  - name: grid
    type: custom
    power:
      source: http
      uri: http://<ess-ip>:8085/api/live
      jq: .grid_power_w
  - name: pv
    type: custom
    power:
      source: http
      uri: http://<ess-ip>:8085/api/live
      jq: '[.ac_power_w, 0] | max'

site:
  meters:
    grid: grid
    pv: [pv]
```

## Monitoring (optional)

The endpoint works well with the Prometheus blackbox exporter, e.g. an `http` module with
`fail_if_body_not_matches_regexp: ['"grid_power_w"']`, so a 503 or an empty answer counts
as down.

## How it works

The LG processes (`PCSMgr`, `PowerMeterMgr`, `ALGMgr`, `DBMgr`, `reportmgr`, `uxmgr`)
exchange data through SysV shared memory (`libclipcomm_system`). D-Bus carries only
control commands. Segment key **1719** (743 bytes, "FromPCS") holds the live inverter and
meter values as a packed struct; the field offsets come from
`AlgMgrShm::GetLogPCSInformation()` in `ALGMgr`. Without `ctypes` the segment cannot be
attached directly, so the service reads it through `/proc/<pid>/mem` of a process that has
it mapped, twice per read, retrying if the two copies differ (a write was in progress).

Details, all segments and how the offsets were derived:
[`docs/reverse-engineering.md`](docs/reverse-engineering.md).

## Security

- Port 8085 has **no authentication**. It only returns read-only measurements, but keep
  the ESS in a trusted LAN and do not forward the port.
- Root SSH on the ESS is a much larger exposure than this service; restrict access to it.

## Changelog

- **2026-11-01** — Home Assistant integration (HACS): config flow with SSH install, sensors, kWh counters, install/update button.
- **2026-11-01** — one thread per connection (max. 16). Before, connections were served
  one after another, and a client slow to send its request stalled all others for up to
  5 s (~2–3 % of 5 s monitoring probes timed out).
- **2026-10-19** — first version.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

Not affiliated with or endorsed by LG Electronics. Use at your own risk; running extra
software on your inverter may affect warranty or support.
