# ATOM Echo Acoustic Mesh — Build Plan

Execution spec for Claude Code. Read fully before writing code. Work phase by phase; each phase has acceptance criteria that must pass before moving on.

## 0. Context and goal

Owner has multiple classic **M5Stack ATOM Echo** (ESP32-PICO-D4, 4MB flash, **no PSRAM**) units — 4 on hand today, but the design isn't capped at that count. Goal: turn them into a whole-home acoustic event detection mesh with a "dumb edge, smart server" architecture:

- Each unit continuously streams raw mic audio over UDP to a LAN server.
- The server runs audio classification (YAMNet) and keyword spotting (openWakeWord) across all streams and publishes detections to MQTT.
- Home Assistant consumes MQTT and drives alerts (Telegram + the units' own speaker/LED as alert beacons), including a dedicated dashboard/app view for configuring the units (not just per-entity toggles scattered across each device's page).
- One detector runs **on-device** and must survive server/network outage: smoke-alarm T3 pattern detection via Goertzel filter.

Existing infra assumed available: Home Assistant, MQTT broker, Docker host (or k8s) on the LAN, ESPHome tooling.

### Hard hardware constraints (do not fight these)

- **No PSRAM** → no on-device ML, no wake word. Device does DSP + streaming only.
- **Pin map (classic ATOM Echo):**
  - Mic SPM1423 (PDM): CLK = GPIO33, DATA = GPIO23
  - Speaker amp NS4168 (I2S): BCLK = GPIO19, LRCLK = GPIO33, SDATA = GPIO22
  - Button = GPIO39, RGB LED (SK6812) = GPIO27
- **GPIO33 is shared** between mic PDM clock and speaker LRCLK → mic and speaker are effectively **half-duplex**. Firmware must stop the mic/stream while playing audio, then resume. Design every playback path around this.
- Speaker is quiet. Alert sounds must be tone bursts in the 2.5–3.5 kHz band, high-passed, near 0 dBFS. No speech for alerts.

### Non-goals

- No fall detection claims. A "thump" detector may be logged as a low-confidence event, but must never page anyone on its own.
- No cloud. All audio stays on the LAN. No recordings persisted by default.

## 1. Repository layout

Single repo `heyra/`:

```
heyra/
├── firmware/
│   ├── components/udp_audio_streamer/   # ESPHome external component (C++)
│   ├── common.yaml                       # shared ESPHome config
│   ├── units/atom-echo-01.yaml, atom-echo-02.yaml, ...  # per-unit: name, room, static IP — one per device, any count
│   └── secrets.yaml.example
├── server/
│   ├── listener/                         # Python service
│   │   ├── ingest.py                     # UDP receiver, per-unit ring buffers
│   │   ├── classify.py                   # YAMNet inference loop
│   │   ├── keywords.py                   # openWakeWord loop
│   │   ├── mqtt_out.py                   # detection → MQTT with hysteresis
│   │   ├── config.yaml                   # units, thresholds, class map
│   │   └── tests/
│   ├── Dockerfile
│   └── docker-compose.yml
├── homeassistant/
│   ├── mqtt_sensors.yaml
│   └── automations.yaml
└── docs/  (this file, calibration notes)
```

## 2. Phase 1 — Firmware (ESPHome)

### 2.1 UDP audio streamer component

Custom ESPHome external component `udp_audio_streamer`:

- Read PDM mic via I2S: **16 kHz, 16-bit, mono**.
- Packetize into UDP datagrams sent to `server_ip:port`. Packet format (little-endian):
  - `magic` u32 = `0x41544D45` ("ATME")
  - `unit_id` u8 (not capped to a fixed fleet size)
  - `flags` u8 (bit0 = streaming paused marker)
  - `seq` u16 (wrapping)
  - `timestamp_ms` u32 (millis since boot)
  - payload: 512 samples (1024 bytes) of PCM → 32 ms per packet, ~31 packets/s, ~260 kbit/s
- Expose an ESPHome `switch` ("Streaming") so HA can pause streaming per unit (privacy toggle, bedrooms). When off, send 1 keepalive/s with the paused flag.
- Expose a `binary_sensor` for the button and a light entity for the SK6812 LED.
- **Half-duplex handling:** provide a service `play_alert(tone_id)` that (1) stops I2S mic + streaming, (2) plays the tone via the speaker, (3) restarts mic + streaming. Alerts are short (≤3 s) synthesized square-wave bursts generated in firmware — no media files, no TTS.

### 2.2 On-device smoke alarm detector

- Goertzel filter bank at **3.0 / 3.2 / 3.4 kHz** over 64 ms windows on the same sample stream.
- Detect the **T3 pattern**: 3 beeps (~0.5 s on / 0.5 s off) + 1.5 s pause, repeating. Require ≥2 full T3 cycles before firing.
- On detection: publish an ESPHome binary_sensor `smoke_alarm_detected` (via native API → HA) AND flash LED red. This path must work with WiFi down for the local LED part.

### 2.3 Shared config

- `common.yaml`: WiFi with static IPs, native API + encryption, OTA, fallback AP, the external component, LED, button. Per-unit files only set: `device_name`, `friendly_name`, `room`, `unit_id`, static IP.
- Button short-press = "acknowledge" event to HA (reuse for the alert-beacon ack loop). Long-press (3 s) = toggle streaming switch locally.

**Acceptance (Phase 1):** flash one unit; `nc -ul <port>` on the server shows well-formed packets at ~31/s with monotonic seq; playing a phone recording of a smoke alarm T3 at ~1 m trips `smoke_alarm_detected` within 10 s; streaming toggle works from HA; `play_alert` interrupts and resumes streaming cleanly.

## 3. Phase 2 — Server listener service

Python 3.11+, single container, CPU-only. No GPU dependency.

### 3.1 Ingest (`ingest.py`)

- One UDP socket. Demux by `unit_id`. Per-unit ring buffer holding ≥2 s of PCM.
- Track per-unit health: last-packet age, packet loss (seq gaps), paused flag. Expose `/healthz` HTTP endpoint with per-unit status. Publish availability to MQTT (`.../status` online/offline, offline after 5 s silence).

### 3.2 Classification (`classify.py`)

- **YAMNet** (TensorFlow Hub model, or tflite equivalent) at native 16 kHz.
- Sliding window: 0.96 s frames, hop 0.48 s, per unit. On CPU this is light for a handful of units; if needed, round-robin units at half rate as the fleet grows.
- Class map in `config.yaml`, initial set:

| event | YAMNet classes (aggregate max) | default threshold | hysteresis |
|---|---|---|---|
| baby_cry | Baby cry, infant cry; Crying, sobbing | 0.45 | 3 hits / 10 s |
| smoke_alarm | Smoke detector, smoke alarm; Fire alarm | 0.40 | 2 hits / 6 s |
| glass_break | Glass; Shatter | 0.50 | 2 hits / 4 s |
| dog_bark | Dog; Bark | 0.55 | 3 hits / 10 s |
| doorbell | Doorbell; Ding-dong | 0.45 | 1 hit |
| shout | Shout, Yell, Screaming | 0.55 | 3 hits / 8 s |
| thump (log-only) | Thump, thud; Bang | 0.60 | 2 hits / 5 s |

- Hysteresis = require N frame-hits within M seconds before an event fires; then a per-event cooldown (default 60 s) before it can fire again. All tunable per unit+event in `config.yaml`.
- `thump` is **log-only**: publish to a diagnostics topic, never to the alerting topic.

### 3.3 Keyword spotting (`keywords.py`)

- **openWakeWord** on the same per-unit streams with custom models for a distress keyword (e.g. "help help" — train/generate model as part of this phase; openWakeWord provides a synthetic-data training path).
- Threshold high (favor precision), 2 activations within 10 s to fire `distress_keyword`.

### 3.4 MQTT output (`mqtt_out.py`)

- Topic scheme:
  - `acoustic/<room>/event` → JSON `{event, score, unit_id, ts}` (retained: no)
  - `acoustic/<room>/status` → `online|offline|paused` (retained)
  - `acoustic/diag/<room>/...` → thumps, health, loss stats
- Publish HA MQTT Discovery configs so sensors auto-appear in HA.

### 3.5 Packaging

- `Dockerfile` (slim, pinned deps), `docker-compose.yml` with restart policy, healthcheck hitting `/healthz`, host network or mapped UDP port. Config + models mounted as volumes. No audio written to disk; add an opt-in debug flag that keeps rolling 30 s WAVs for calibration only.

**Acceptance (Phase 2):** with 1 live unit, playing YouTube clips of baby crying / glass break / doorbell each produce exactly one MQTT event with correct room; TV at normal volume for 1 h produces no alert-topic events; killing a unit flips its status to offline within 5 s; container survives restart with no manual steps.

## 4. Phase 3 — Home Assistant integration

- MQTT sensors per room+event (via discovery from Phase 2; keep `mqtt_sensors.yaml` only as fallback/reference).
- A dedicated Lovelace dashboard (or custom panel) listing every unit together for at-a-glance configuration (streaming on/off, room label, per-unit thresholds) — not just each unit's auto-generated per-device page — regardless of how many units are deployed.
- Automations (`automations.yaml`, adapt entity names):
  1. **smoke_alarm** (either on-device sensor OR server event) → Telegram message with room + all units `play_alert(tone=critical)` + LEDs red. Button press on any unit → ack: stop tones, LEDs green 5 s, Telegram "acked by <room>".
  2. **baby_cry** → notify only chosen targets, LED amber on chosen units, quiet hours respected.
  3. **glass_break** → Telegram + LEDs, only when nobody home (use existing presence).
  4. **distress_keyword** → Telegram with high priority + repeat every 60 s until button-ack.
  5. **doorbell / dog** → normal notifications, no beacons.
- Per-unit streaming toggles exposed on a dashboard; bedroom units default-off schedule if desired.

**Acceptance (Phase 3):** end-to-end smoke test: phone plays T3 tone → within 15 s Telegram arrives and all units beep/flash → pressing any button silences everything and sends the ack message.

## 5. Phase 4 — Calibration and hardening

- Enable debug WAV capture; walk the house triggering each event class from realistic distances (same room, adjacent room, through door). Record hit/miss per unit; adjust thresholds/hysteresis in `config.yaml`.
- False-positive soak: 48 h of normal life; target **zero** alert-topic false fires for smoke/glass/distress; baby_cry/dog tuned to taste.
- Document final thresholds in `docs/calibration.md`. Disable debug capture.
- Optional stretch (separate branch, only after the above is green): BLE presence scanning ride-along in firmware; washing-machine end-jingle class; per-unit mic gain normalization.

## 6. Ground rules for implementation

- Pin every dependency version (ESPHome, TF/tflite, openWakeWord, paho-mqtt).
- No audio persisted outside the opt-in debug mode; state it in the README.
- Keep firmware component generic (no hardcoded rooms/IPs, no hardcoded unit count — everything via substitutions).
- Prefer boring code over clever DSP; the Goertzel detector and packetizer must be unit-testable on host (feed WAV fixtures through the same C++/Python logic where feasible).
- Commit per phase; each phase's acceptance criteria go in the PR description with actual test evidence.

The project name is Heyra.
