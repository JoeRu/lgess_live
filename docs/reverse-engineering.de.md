# LG ESS ED05K000E00 – Analyse der Echtzeitwerte

Stand: 2026-10-19

## Ziel

Das LG ESS (Batteriewechselrichter, ohne Herstellergarantie) schreibt Messwerte nur alle 15 Minuten in
`/nvdata/DBFiles/ems_DEU.db`. pv_sync liest genau diese Datenbank. Für evcc werden aber Live-Leistungswerte
im Sekundenbereich benötigt. Untersucht wurde, ob es solche Werte auf dem Gerät gibt und wie man sie liest.

**Ergebnis: Ja.** Die Werte liegen sekündlich aktualisiert im Shared Memory. Der Dienst `lgess_live` stellt sie
seit 2026-10-19 unter `http://<ess-ip>:8085/api/live` bereit.

## System

| | |
|---|---|
| Hostname | `lge-ems` (Avahi: `lge-ems-5.local`) |
| Kernel | Linux 3.10.17, armv7l (i.MX6), BusyBox 1.21.1 |
| Zugang | `ssh root@<ess-ip>`, kein Passwort |
| Offene Ports (vorher) | 22 (ssh), 111 (rpcbind). Kein Web-/API-Port |
| Python | 2.7.3, unvollständig: **kein** `ctypes`, `json`, `BaseHTTPServer`. `site` defekt, daher nur mit `python -S` |
| Root-FS | ext3, beschreibbar (`/dev/mmcblk0p3`) |
| Init | SysV, Runlevel 5 (`/etc/rc5.d`) |
| Batterie | defekt und abgeklemmt, daher alle `batt_*`-Werte = 0 |

### Prozesse

| Prozess | Aufgabe |
|---|---|
| `PCSMgr` | Kommunikation mit dem Wechselrichter-DSP (PCS) |
| `PowerMeterMgr` | Netzzähler über Modbus (`libmodbus`) |
| `ALGMgr` | Regelalgorithmus (Laden/Entladen/Einspeisung), sendet Befehle an PCSMgr |
| `DBMgr` | schreibt Quartals-/Tages-/Wochen-/Monatswerte in SQLite |
| `reportmgr` | Upload an die LG-Cloud (EnerVu), ebenfalls 15-Min-Werte (`PMSInfo::Set15MinPowerData`) |
| `uxmgr` | Touch-Display-Oberfläche |
| `ProcMonMgr` | Watchdog für die Manager-Prozesse |

## Kommunikationswege

### D-Bus (nur Steuerung)

Mit `dbus-monitor --system` mitgeschnitten (rein passiv). Über D-Bus laufen nur Steuerbefehle, keine Messwerte:

- `ems.signal.alomgr` / `alomgr_to_pcs`: ALGMgr → PCS, JSON `{"cmds":[{"start":"45000","data":[...,"<counter>"]}]}`
  (Registerblock 45000, jede Sekunde mit hochzählendem Heartbeat)
- `ems.signal.pcsmgr` / `pcs`: Rückmeldungen `{"evt":"write_success"}`, `{"evt":"warn_continue"}`

### SysV Shared Memory (Messwerte)

`libclipcomm_system.so` stellt die Klasse `clipShmem(key, size)` bereit. Gesperrt wird über POSIX-Semaphoren
`/dev/shm/sem.clipShMemLock-<key>`. Alle Segmente haben die Rechte 0666. Die Zuordnung von Key und Größe stammt aus den
`clipShmem::clipShmem(unsigned, unsigned)`-Aufrufen in ALGMgr, DBMgr und reportmgr:

| Key | Größe | Ersteller | Bedeutung |
|---|---|---|---|
| **1719** | 743 | PowerMeterMgr | **FromPCS**: Live-Werte von Wechselrichter und Zähler (gepackte Struct) |
| 1205 | 213 | ALGMgr | **DBAccum**: laufende 15-Min-Akkumulatoren (W·s) plus Werte des letzten Quartals |
| 1605 | 9364 | ALGMgr | Ringpuffer mit Sekunden-Samples (52-Byte-Records inkl. Unix-Zeit und Frequenz) |
| 1604 | 12244 | ProcMonMgr | Prozessüberwachung (Heartbeat-Zähler) |
| 1208 | 158 | uxmgr | AlgWrite / UX-Kontext |
| 1702 | 522 | PCSMgr | ToPCS (Befehle an den Wechselrichter) |
| 1206 | 160 | netmgr | Netzwerkstatus (Zeitzähler) |
| 1207, 1309, 1602, 1603 | – | – | Konfiguration und Status (statisch) |

## Reverse Engineering von FromPCS (Key 1719)

Die Binaries sind gestrippt, exportieren aber die C++-Symbole dynamisch. Damit war die Analyse direkt möglich.

1. `AlgMgrShm` hält die SHM-Zeiger als Member: `GetToPCS()` → `this+48`, **`GetFromPCS()` → `this+52`**,
   `GetAlgWrite()` → `this+56`, `GetNVRAM()` → `this+60`, `GetDBAccum()` → `this+64`.
2. `AlgMgrShm::GetLogPCSInformation()` (ALGMgr @ `0x24bf4`) weist erst 17 Label-Strings zu und formatiert
   dann für jedes Label einen Wert aus `FromPCS` per `sprintf`. Aus `ldr r2, [r3, #off]` ergibt sich der Offset,
   aus `vcvt.f64.f32` bzw. dem Format (`%.3f` oder `%5d`) der Typ.
3. Gegenprobe am Speicherabzug: Offset 331 als float = 50,05 Hz. FromPCS ist also Key 1719.

| Label (aus ALGMgr) | Offset | Typ | Format |
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

Die Struct ist gepackt, die Offsets sind deshalb nicht 4-Byte-aligned. Alle Werte sind Little Endian.

### Plausibilisierung

Live-Wert gegen den DB-Quartalswert (16:15, `tbl_record_quarter`):

| | Live (SHM 1719) | DB-Quartal |
|---|---|---|
| PV | 1303 + 1027 = 2330 W DC, AC 2146 W | `pv_power` 2216 |
| Netz | Meter −1332 W | `grid_feed_in` 1339, `grid_power_purchase` 0 |
| Verbrauch | AC + Meter = 814 W | `load_power` 876 |

Daraus folgt: **Meter Power ist positiv bei Netzbezug und negativ bei Einspeisung.** Das entspricht der Konvention von evcc.
Hausverbrauch = AC-Leistung + Meter-Leistung.

Weitere Beobachtungen:
- Segment 1205 enthält die Werte des letzten Quartals (Offset 84 = 2216 `pv_power`, 168 = 1339 `grid_feed_in`,
  124 = 876 `load_power`) sowie den Quartalszeitstempel (Offset 68). Daraus füllt DBMgr die Datenbank.
- `reportmgr` erzeugt das Cloud-JSON (`currentInfo`: `pvP`, `loadP`, `gridP`, `battChg`, …) in
  `CommReportServer::testRepotPowerBody3` aus einer Struct mit `std::string`-Feldern. Die Quelle sind ebenfalls 15-Min-Daten.
- Nicht verifiziert: das Vorzeichen von `BATT Power` (Laden oder Entladen), weil die Batterie abgeklemmt ist.

## Der Dienst `lgess_live`

- Datei `lgess_live.py` (Python 2.7, `python -S`, nur `os`, `socket`, `struct`, `thread`, `time`; seit 2026-11-01 ein Thread pro Verbindung)
- Sucht über `/proc/*/maps` einen Prozess, der `/SYSV000006b7` eingeblendet hat, und liest das Segment über
  `/proc/<pid>/mem`. Ohne `ctypes` gibt es keinen Zugriff auf den Lock-Semaphor. Deshalb wird zweimal gelesen,
  bis beide Lesungen übereinstimmen. Startet ein LG-Prozess neu, sucht der Dienst die Einblendung automatisch neu.
- Die LG-Prozesse werden nur gelesen, nicht verändert. Der Dienst belegt etwa 4 MB RAM und puffert Werte für 1 s.
- HTTP auf Port **8085**: `GET /api/live` (auch `/` und `/live`) liefert JSON, andere Pfade 404, bei Lesefehler 503.

### Ausgabe

```json
{"ac_freq_hz": 49.970, "ac_power_w": 1660, "batt_current_a": 0.000, "batt_power_w": 0,
 "batt_soc_pct": 0.000, "batt_status": 0, "batt_voltage_v": 79.400, "dc_link_v": 625,
 "grid_export_w": 856.340, "grid_import_w": 0.000, "grid_power_w": -856.340,
 "load_power_w": 803.660, "meter_freq_hz": 50.060, "meter_power_w": -856.340,
 "pv1_current_a": 2, "pv1_power_w": 1075, "pv1_voltage_v": 376,
 "pv2_current_a": 2, "pv2_power_w": 750, "pv2_voltage_v": 308,
 "pv_power_w": 1825, "timestamp": 1792420455}
```

Abgeleitete Felder: `pv_power_w = pv1 + pv2` (DC), `grid_power_w = meter_power_w`,
`grid_import_w` und `grid_export_w` (jeweils ≥ 0), `load_power_w = ac_power_w + meter_power_w`.

### Installation auf dem Gerät (am 2026-10-19 durchgeführt)

| Pfad | |
|---|---|
| `/usr/local/lgess_live/lgess_live.py` | Dienst |
| `/etc/init.d/lgess_live` | Init-Skript (`start`, `stop`, `restart`, über `start-stop-daemon`) |
| `/etc/rc5.d/S95lgess_live` | Autostart |
| `/var/run/lgess_live.pid` | PID-Datei |

```sh
./install.sh <ess-ip>      # installieren bzw. aktualisieren und neu starten
./uninstall.sh <ess-ip>    # vollständig entfernen
ssh root@<ess-ip> /etc/init.d/lgess_live restart
```

Ein Firmware-Update von LG könnte die Dateien überschreiben oder die Struct-Offsets ändern. In diesem Fall die
Offsets wie oben über `GetLogPCSInformation` neu bestimmen.

## Einbindung

Die Konfiguration für evcc und Home Assistant steht in `README.md`. Energiezähler (kWh) erzeugt man in Home Assistant mit dem Helfer
„Integral (Riemann-Summe)“. pv_sync bleibt für die DB-Historie (Tag/Woche/Monat) nutzbar.

## Offene Punkte

- Vorzeichen von `batt_power_w` prüfen, falls wieder eine Batterie angeschlossen wird.
- Optional: MQTT-Push statt HTTP-Pull (es gibt keine Bibliothek, das Protokoll müsste von Hand über `socket` umgesetzt werden).
- Optional: Ringpuffer 1605 und DBAccum 1205 vollständig dekodieren (Sekundenhistorie, laufende Quartalsenergie).
- Sicherheit: Port 8085 ist ohne Authentifizierung im LAN erreichbar und liefert nur Lesewerte. SSH als root ohne Passwort war schon vorher offen.

## Analyse-Artefakte

- `re/` (nicht im Repository): ARM-Disassembly (`*.S`), `xref.py`, `keymap.py`, `pcs_fields.py`
- `device/` (nicht im Repository: LG-Binärdateien): Kopien der Bibliotheken und Binaries vom Gerät, SHM-Dumps (`shm_*.txt`), D-Bus-Mitschnitt, DB-Kopie
