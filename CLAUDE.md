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
  atom-echo-01 unit. Source of truth moved to `addons/heyra-listener/` (see the AxeForging
  Add-ons entry below) — `cd server && docker compose up --build -d` still runs it locally
  for non-HA users (builds from `../addons/heyra-listener`, own dedicated mosquitto, not
  shared with gjallarhorn).
  - 36/36 unit tests pass (`addons/heyra-listener/listener/tests/` +
    `addons/heyra-listener/test_render_config.py`, no hardware/Docker needed).
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
  `addons/heyra-listener/listener/mqtt_out.py` actually expose; all 3 YAML files parse
  cleanly. See `homeassistant/README.md` for the setup checklist — note this file predates
  the AxeForging Add-ons below and its "no custom Add-on" reasoning has since been
  superseded; `addons/heyra-listener` now covers the MQTT/config side natively.
- **AxeForging HA Add-ons + hardware abstraction + public release** — built this session,
  live-verified locally (not yet against a real Supervisor instance). Two Add-ons under
  `addons/`, one repo (`repository.yaml` at root, Stage E):
  - `addons/heyra-listener/` — the Phase 2 service, packaged as a real Add-on. `options`/
    `schema` exposes the `units` list (HA-native Configuration UI — this is the "a view to
    configure the units" ask from the very start of the project). `services: [mqtt:want]`
    auto-discovers the official Mosquitto broker Add-on if installed (added real
    username/password support to `MqttConfig`/`MqttPublisher` for this — didn't exist
    before). `map: [addon_config:rw]` lets advanced users drop a full replacement
    `config.yaml` for per-event tuning without a rebuild — `server/docker-compose.yml`'s
    local dev path uses the same override mechanism via a bind mount, so both environments
    exercise identical code. Kept `python:3.11-slim-bookworm` as the base image, not HA's
    Alpine-based one (the numpy/tflite-runtime ABI landmine above is exactly the kind of
    thing Alpine/musl reintroduces). Models are baked into the image (Add-on volumes can't
    reach arbitrary host paths) — live-verified via `docker compose up --build` and a
    standalone `docker build`, both against the real atom-echo-01 unit still streaming.
  - `addons/heyra-flasher/` — new: compiles/flashes Heyra firmware onto units over USB from
    an Ingress panel inside HA, instead of the `esphome` CLI from a dev machine. `uart: true`
    (mirrors the real ESPHome Add-on's own config, confirmed via direct fetch of
    `github.com/esphome/home-assistant-addon`). Small Starlette+uvicorn app: board dropdown
    (from `firmware/boards/`) → unit/WiFi form → shells `esphome compile` then
    `esphome upload`, streams output live. Needed Python 3.12 (esphome 2026.7.3's own
    requirement) and had to pin `starlette==0.52.1`/`uvicorn==0.40.0` below esphome's own
    `platformio` dependency's caps (`<0.53`/`<0.41`) — not a free choice, esphome's
    transitive constraint. Docker build context can't reach outside an Add-on's own folder,
    so `firmware/{common.yaml,boards/,components/}` are copied (not symlinked — symlinks
    escaping the build context aren't reliably followed) into
    `addons/heyra-flasher/firmware/` — **known duplication, keep in sync manually until a
    better build-context solution exists.**
  - `firmware/boards/` (Stage A prerequisite for the flasher's board dropdown), new `scream`
    event (Stage B), `help_en`/`socorro_pt` keyword scaffolding (Stage C) — see their own
    status lines above.
  - Not yet done: `repository.yaml`, root `README.md`, `LICENSE`, Add-on icons (rasterized
    from the real AxeForging brand kit), the public `github.com/AxeForging/heyra` repo
    itself, and the GitHub Pages landing site — all planned as later stages in the same
    session, see the plan file referenced at the top of Phase 1 for the full 6-stage plan.
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
