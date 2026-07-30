# Heyra

Detects smoke alarms, baby crying, glass breaking, dog barks, and doorbells
by sound, and tells Home Assistant — plus flashes new ATOM Echo units over
USB from a panel inside HA, no dev machine needed. Under the hood: YAMNet +
openWakeWord classification, published via MQTT Discovery.

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

- **`units`** — one entry per ATOM Echo unit (`unit_id` matches the
  firmware's `unit_id` substitution, `room` is used in entity names/MQTT
  topics). This is the only setting exposed through the Add-on's
  Configuration tab.

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
touch. To override them (or to point `mqtt.host` at your own broker): drop
a full `config.yaml` (same shape as `addons/heyra/listener/config.yaml` in
the source repo) at this Add-on's config directory (Settings →
Apps/Add-ons → Heyra → Add-on Config folder) — if present, it fully
replaces the built-in template. Restart the Add-on to pick up changes.

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
