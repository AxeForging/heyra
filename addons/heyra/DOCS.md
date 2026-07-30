# Heyra

Detects smoke alarms, baby crying, glass breaking, dog barks, and doorbells
by sound, and tells Home Assistant. Under the hood: YAMNet + openWakeWord
classification, published via MQTT Discovery. New units are flashed from
your browser at [axeforging.github.io/heyra/flash.html](https://axeforging.github.io/heyra/flash.html)
— nothing to install on this Add-on for that.

## Required: an MQTT broker

**This Add-on needs a real MQTT broker to publish anything — without one,
it starts fine but every event silently fails to reach Home Assistant**
(you'll see `mqtt connection error` retrying forever in the Log tab).
Two ways to satisfy this:

1. **Recommended**: install the official **Mosquitto broker** Add-on
   (Settings → Apps/Add-ons → Add-on Store → search "Mosquitto broker" →
   Install → Start). Heyra auto-discovers it (`services: [mqtt:want]`) —
   no further setup.
2. Already have a different broker? Point Heyra at it via "Advanced
   tuning" below (`mqtt.host`/`mqtt.port` in a config override) — the
   built-in default (`mqtt.host: mosquitto`) only resolves inside this
   repo's local `docker-compose` dev setup, not on a real HA instance.

## Configuration

- **`units`** — one entry per ATOM Echo unit (`unit_id` is what you assign
  the physical device to below in the Ingress panel, `room` is used in
  entity names/MQTT topics). This is the only setting exposed through the
  Add-on's Configuration tab.

## The Ingress panel

Open the panel (sidebar icon) to see your configured units and whether
they're currently online, pulled live from the same data `/healthz` serves
(below). It also links out to the WebSerial flasher for adding a new unit.

Below that, **Devices found on your network** lists any Heyra unit it
discovers via mDNS, along with the Unit ID it's currently reporting — pick
which configured unit it is and hit **Assign** to push the correct ID
straight to the device. This is the one place to set it; there's no need to
separately visit the device's own local page.

## Flashing a new unit

Handled entirely by [axeforging.github.io/heyra/flash.html](https://axeforging.github.io/heyra/flash.html)
in your browser — no dev machine, nothing installed here. One shared
firmware image works for every unit; after flashing, connect to the unit's
own open Wi-Fi hotspot to give it your real network. Once it's online, it
shows up under **Devices found on your network** above — assign it there.
Requires a desktop build of Chrome or Edge (WebSerial isn't available in
Firefox, Safari, or on mobile).

## Advanced tuning

Per-event thresholds, hysteresis, cooldowns, and off-delays aren't exposed
in the Configuration tab — they're still provisional pending Phase 4
calibration, and would be a lot of UI surface for values you'd rarely
touch. To override them (or to point `mqtt.host` at your own broker): drop
a full `config.yaml` (same shape as `addons/heyra/listener/config.yaml` in
the source repo) at this Add-on's config directory (Settings →
Apps/Add-ons → Heyra → Add-on Config folder) — if present, it fully
replaces the built-in template. Restart the Add-on to pick up changes.

## Ports

- `6969/udp` — raw audio ingest from firmware units (fixed, matches every
  unit's `server_port` — there's no per-unit config to keep in sync anymore).
- `8080/tcp` — `/healthz` status endpoint (also what the Ingress panel
  reads from, over loopback).
- Ingress panel — device status, no separate port to remember.

## New alert types

`scream` and two provisional keyword slots (`help_en`/`socorro_pt`) exist
in the config template. The keyword slots need a trained model before they
do anything — see `docs/wake-word-training.md` in the source repo.

## What flashing doesn't do (yet)

- USB only — no OTA for a unit's first flash. A unit already on your
  network can still be re-flashed over the air with the `esphome` CLI
  directly, or via the official ESPHome Add-on if you have it installed.
- No log tailing after flashing — add the ESPHome integration in Home
  Assistant (Settings → Devices & Services) to see a unit's logs and
  entities once it's on your network.
