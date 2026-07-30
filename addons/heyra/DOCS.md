# Heyra

Runs the acoustic classification pipeline (YAMNet event detection +
openWakeWord keyword spotting) for your Heyra ATOM Echo mesh, publishes
detections to Home Assistant via MQTT Discovery, and lets you flash new
units over USB from a panel inside HA — one Add-on, no dev machine needed.

## Configuration

- **`units`** — one entry per ATOM Echo unit (`unit_id` matches the
  firmware's `unit_id` substitution, `room` is used in entity names/MQTT
  topics). This is the only setting exposed through the Add-on's
  Configuration tab.
- **MQTT** — if you have the official Mosquitto broker Add-on installed,
  this Add-on auto-discovers it (`services: [mqtt:want]`), no setup needed.
  Otherwise it falls back to the built-in template's `mqtt.host` (see
  "Advanced tuning" below to point it elsewhere).

## The Ingress panel

Open the panel (sidebar icon) for two things:
- **Live status** links to `<host>:8080/healthz` for per-unit online/offline
  JSON (not proxied through Ingress, open it directly on your network).
- **Flash a unit** — pick a board (from `firmware/boards/`), fill in room/
  WiFi/unit details, hit Flash. Streams the real `esphome compile`/
  `esphome upload` output live. USB-serial access (`uart: true`) is granted
  automatically; if your device doesn't show up in the port list, unplug/
  replug it and reload.

## Advanced tuning

Per-event thresholds, hysteresis, cooldowns, and off-delays aren't exposed
in the Configuration tab — they're still provisional pending Phase 4
calibration, and would be a lot of UI surface for values you'd rarely
touch. To override them: drop a full `config.yaml` (same shape as
`addons/heyra/listener/config.yaml` in the source repo) at this Add-on's
config directory (Settings → Add-ons → Heyra → Add-on Config folder) — if
present, it fully replaces the built-in template. Restart the Add-on to
pick up changes.

## Ports

- `6969/udp` — raw audio ingest from firmware units (must match
  `server_port` in your `firmware/units/*.yaml`).
- `8080/tcp` — `/healthz` status endpoint.
- Ingress panel — status + flashing wizard, no separate port to remember.

## New alert types

`scream` and two provisional keyword slots (`help_en`/`socorro_pt`) exist
in the config template. The keyword slots need a trained model before they
do anything — see `docs/wake-word-training.md` in the source repo.

## What flashing doesn't do (yet)

- No OTA flashing (USB only) — a unit already on your network can still be
  re-flashed with the `esphome` CLI directly, or via the official ESPHome
  Add-on if you have it installed.
- No log tailing after flashing — add the ESPHome integration in Home
  Assistant (Settings → Devices & Services) to see a flashed unit's logs
  and entities.
