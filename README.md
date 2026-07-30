<p align="center">
  <img src="addons/heyra-listener/logo.png" alt="Heyra" width="250">
</p>

<p align="center">
  Acoustic event detection mesh for Home Assistant, built by
  <a href="https://github.com/AxeForging">AxeForging</a>.
</p>

# Heyra

"Dumb edge, smart server" acoustic event detection. Cheap ESP32 units
(M5Stack ATOM Echo today, more boards welcome) stream raw audio to a server
that runs it through YAMNet + openWakeWord and publishes detections to Home
Assistant over MQTT — baby crying, a smoke alarm going off, glass breaking, a
dog barking, someone at the door, shouting, screaming, and a couple of
provisional wake-word slots for shouting for help. The smoke-alarm detector
also runs entirely on-device, so it still works if the server or your
network goes down.

## Features

- **Baby cry**, **smoke alarm** (dual-path: on-device + server, survives an
  outage), **glass break**, **dog bark**, **doorbell**, **shout**,
  **scream** — all via YAMNet audio classification, no network round-trip
  needed for the smoke alarm.
- **Wake-word slots** for "help" (English) and "socorro" (Portuguese) — the
  pipeline is wired end-to-end, real trained models are the next step (see
  [`docs/wake-word-training.md`](docs/wake-word-training.md)).
- **MQTT Discovery** — entities show up in Home Assistant automatically, no
  manual YAML.
- **Privacy-first** — no audio persisted anywhere outside an explicit
  opt-in debug mode. Raw PCM never leaves the LAN.
- Any number of units — not capped at a fixed fleet size.

## Install

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   → add `https://github.com/AxeForging/heyra`.
2. Install **Heyra Listener** (the detection service) and, if you're
   flashing new units, **Heyra Flasher** (compiles/flashes firmware over
   USB from a panel inside HA — no dev machine or CLI needed).
3. See [`homeassistant/README.md`](homeassistant/README.md) for the full
   setup checklist (MQTT, notifications, automations).

## Compatible hardware

| Board | Status |
|---|---|
| M5Stack ATOM Echo | Verified, in production use |

Built to add more — see [`firmware/boards/README.md`](firmware/boards/README.md)
for the hardware contract a new board profile needs to satisfy.

## Repo layout

```
firmware/          ESPHome firmware + the udp_audio_streamer component (Goertzel/T3 smoke detection)
addons/             Home Assistant Add-ons (heyra-listener, heyra-flasher)
homeassistant/      Automations, dashboard, MQTT reference config
server/             Plain docker-compose deployment, for non-HA users
docs/               Build plan, wake-word training runbook
web/                Project landing page
```

Full architecture and status: [`CLAUDE.md`](CLAUDE.md).

## From AxeForging

Built by [Murilo Machado](https://github.com/murilopmachado) and the
[AxeForging](https://github.com/AxeForging) team. Check out our other
tools at [tools.axeforge.io](https://tools.axeforge.io).

## License

[MIT](LICENSE)
