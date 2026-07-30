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
- Phases 2-4 (server ML, HA integration, calibration) — not started.

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
