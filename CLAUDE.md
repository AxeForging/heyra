# Heyra — ATOM Echo Acoustic Mesh

"Dumb edge, smart server" acoustic event detection mesh built on M5Stack ATOM Echo units
(ESP32-PICO-D4, no PSRAM). Full spec: `docs/build-plan.md`.

## Status

- **Phase 1 (firmware)** — done, verified against real hardware (atom-echo-01, MAC
  14:2b:2f:a1:5a:e8, static IP 192.168.1.101). See
  `/home/oa/.claude/plans/atom-echo-acoustic-snuggly-heron.md` for the detailed design.
  - Packet stream: ~32/s, monotonic seq, zero gaps observed.
  - Streaming switch: verified pause (keepalive-only) and resume, seq continuous throughout.
  - `play_alert`: verified mic stop/tone/resume, seq continuous (no reset) after the gap.
  - Smoke alarm T3 detection: verified end-to-end (mic -> Goertzel -> T3Detector ->
    binary_sensor -> LED) against a synthesized 3kHz T3 tone played over computer
    speakers, repeatedly and reliably. `BEEP_AMPLITUDE_THRESHOLD` (goertzel.cpp) and the
    per-phase tolerances (t3_detector.h) were retuned from their initial guesses using
    real magnitude/timing readings off the device — both are explicitly flagged in-code as
    provisional pending Phase 4 calibration against an actual smoke-alarm recording.
- **Phase 2 (server: YAMNet + openWakeWord + MQTT)** — done, verified against the live
  atom-echo-01 unit. `cd server && docker compose up --build -d` runs it (own dedicated
  mosquitto, not shared with gjallarhorn).
  - 32/32 unit tests pass (`server/listener/tests/`, no hardware/Docker needed).
  - New `scream` event (YAMNet class 11, "Screaming") split out of `shout` (was folded in as
    `[6, 9, 11]`, now `shout` is `[6, 9]` and `scream` owns 11 exclusively) — avoids double
    notification for the same sound. Thresholds provisional pending Phase 4, same as every
    other event.
  - `tflite-runtime==2.14.0`'s compiled extension is ABI-incompatible with numpy 2.x
    (predates numpy 2.0) — pinned `numpy==1.26.4`, not the originally-planned 2.2.6.
  - Verified live: UDP ingest (~32 pkt/s, zero gaps, `/healthz` correct), real YAMNet
    classification firing a correct `baby_cry` MQTT event (score 0.5) on a real baby-cry
    recording, container restart resilience (auto-resumes online, no manual steps).
  - A doorbell chime SFX correctly scored high on YAMNet's "Chime"/"Bell" classes but not
    the narrower "Doorbell"/"Ding-dong" classes configured for that event — pipeline is
    correct, class-mapping/threshold tuning against real fixtures is Phase 4 work as
    already anticipated.
  - Not run this session (flagged as follow-ups, not blockers): the 1h TV soak test, and
    physically power-cycling a unit to verify the offline-after-5s status transition
    (covered by unit tests via synthetic timestamps, not live hardware).
  - `keyword_spotting` uses openWakeWord's stock `hey_jarvis` model as a placeholder —
    `distress_keyword` is NOT a trained "help help" model yet, by design (see Context in
    the Phase 2 plan). Swapping in a real one is a `config.yaml` change, no rebuild.
  - `keyword_spotting` is now a list (was a single entry) — added `help_en`/`socorro_pt`
    slots pointing at model files that don't exist yet. `main.py` logs a warning and skips
    starting a spotter for a missing model instead of crashing; `mqtt_out.py` withholds
    that event's HA discovery entity until the file is present. See
    `docs/wake-word-training.md` for the actual training runbook (openWakeWord is
    officially English-only; Portuguese is unproven DIY territory) — training itself is
    deliberately deferred, same bucket as Phase 4 calibration.
- **Phase 3 (Home Assistant integration)** — config generated, **live-checked but not
  live-fired**. The real HA instance is `http://homeassistant.local:8123/` (HA 2026.7.3,
  Home Assistant OS/Supervised, same subnet as this dev machine — the earlier
  `192.168.31.0/24` address in `hass-mcp`'s MCP config was stale). Queried live via a
  Long-Lived Access Token: `hassio` present, `esphome` absent (integration not added yet),
  `mqtt` present but pointed at a different broker than Heyra's dedicated mosquitto,
  `telegram_bot` absent, `mobile_app` present with 3 registered devices. `automations.yaml`
  now calls `notify.notify` (real, broadcasts to all 3 phones) instead of Telegram
  placeholders. Still outstanding before the manual test in `homeassistant/README.md` can
  run: add the ESPHome integration, repoint Heyra's MQTT config at HA's existing broker.
  All entity/service names cross-checked against what `firmware/common.yaml` and
  `server/listener/mqtt_out.py` actually expose; all 3 YAML files parse cleanly. See
  `homeassistant/README.md` for the full checklist, including why a custom HA Add-on
  wasn't built and how to use the official ESPHome Add-on for flashing instead of the CLI.
- Phase 4 (calibration) — not started.

## Frozen contract: UDP audio packet format

Firmware → server, little-endian, one packet per 32ms of audio (512 samples @ 16kHz/16-bit/mono).
Any change here is a breaking change to both the firmware component and the (future) server —
treat as frozen once Phase 2 starts consuming it.

| field | type | offset | notes |
|---|---|---|---|
| `magic` | u32 | 0 | `0x41544D45` ("ATME") |
| `unit_id` | u8 | 4 | 1..255, not capped to a fixed fleet size |
| `flags` | u8 | 5 | bit0 = streaming paused (payload omitted, 1 keepalive/s) |
| `seq` | u16 | 6 | wrapping, mod 65536 |
| `timestamp_ms` | u32 | 8 | millis() since boot |
| payload | 1024 bytes | 12 | raw PCM, 512 samples, absent when paused |

Struct is `__attribute__((packed))`; total size 1036 bytes when payload is present, 12 bytes
(header only) for paused keepalives. See `firmware/components/udp_audio_streamer/packet.h`.

## Unit count

Not fixed. The owner has 4 physical units today; the firmware/config pattern (`common.yaml` +
one `units/atom-echo-NN.yaml` per device) supports any number — add or remove unit files freely.
