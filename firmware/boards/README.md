# Board profiles

One file per supported board. One shared image serves every physical unit of
a given board (see `common.yaml`'s runtime `unit_id`/DHCP/mDNS setup) --
compiled directly against `../common.yaml` as an ESPHome `packages:` entry,
no per-unit wrapper file needed:

```yaml
packages:
  board: !include ../boards/<board>.yaml
  base: !include ../common.yaml
```

## Hardware contract

`common.yaml` is board-agnostic — it never references a GPIO pin directly.
Instead it references entities by `id`, which every board file must define:

| id | component | used by |
|---|---|---|
| `mic` | `microphone:` | `udp_audio_streamer` (`microphone_id: mic`) |
| `spk` | `speaker:` | `udp_audio_streamer` (`speaker_id: spk`), `play_alert` |
| `status_led` | `light:` | smoke-alarm strobe (`common.yaml`), button-ack automations |
| `button` | `binary_sensor: platform: gpio` | ack event (`esphome.button_ack`), streaming toggle (long-press) |

Fixed assumptions a new board must also satisfy (not yet parameterized):

- **Audio format: 16kHz, 16-bit, mono.** Hardcoded as C++ constants across
  `components/udp_audio_streamer/{packet.h,goertzel.h,tone_synth.h,udp_audio_streamer.cpp}`
  — not read from the `microphone:`/`speaker:` YAML config at runtime. A board
  running a different sample rate needs those constants changed too, not just
  a new board file.
- **No PSRAM.** `udp_audio_streamer.cpp`'s alert-tone rendering and
  `tone_synth.h` are deliberately chunked (never render a whole tone into one
  buffer) because the reference hardware (ESP32-PICO-D4) has none. Safe for a
  PSRAM-equipped board too (just an unnecessary constraint there), not
  something that breaks.
- The custom `udp_audio_streamer` component itself takes `microphone_id`/
  `speaker_id` as config (see `components/udp_audio_streamer/__init__.py`) —
  it never touches a pin number directly, so it needs no changes to support a
  new board.

## Compatible hardware

| Board | Status |
|---|---|
| M5Stack ATOM Echo (ESP32-PICO-D4, no PSRAM) | Verified — see `atom-echo.yaml`, in production use |

Nothing else is verified yet. Adding a board means: a new `boards/<name>.yaml`
defining the four ids above (electrical specifics — mic/speaker chip, LED
type, button pin/pull — go here), a note in this table, and a real board to
test against before calling it "supported." Don't add speculative entries for
hardware nobody has actually flashed.
