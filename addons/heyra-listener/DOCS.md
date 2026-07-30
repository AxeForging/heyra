# Heyra Listener

Runs the acoustic classification pipeline (YAMNet event detection +
openWakeWord keyword spotting) for your Heyra ATOM Echo mesh, and publishes
detections to Home Assistant via MQTT Discovery.

## Configuration

- **`units`** — one entry per ATOM Echo unit (`unit_id` matches the
  firmware's `unit_id` substitution, `room` is used in entity names/MQTT
  topics). This is the only setting exposed through the Add-on's
  Configuration tab.
- **MQTT** — if you have the official Mosquitto broker Add-on installed,
  this Add-on auto-discovers it (`services: [mqtt:want]`), no setup needed.
  Otherwise it falls back to the built-in template's `mqtt.host` (see
  "Advanced tuning" below to point it elsewhere).

## Advanced tuning

Per-event thresholds, hysteresis, cooldowns, and off-delays aren't exposed
in the Configuration tab — they're still provisional pending Phase 4
calibration, and would be a lot of UI surface for values you'd rarely
touch. To override them: drop a full `config.yaml` (same shape as
`addons/heyra-listener/listener/config.yaml` in the source repo) at this
Add-on's config directory (Settings → Add-ons → Heyra Listener →
Add-on Config folder) — if present, it fully replaces the built-in
template. Restart the Add-on to pick up changes.

## Ports

- `6969/udp` — raw audio ingest from firmware units (must match
  `server_port` in your `firmware/units/*.yaml`).
- `8080/tcp` — `/healthz` status endpoint.

## New alert types

`scream` and two provisional keyword slots (`help_en`/`socorro_pt`) exist
in the config template. The keyword slots need a trained model before they
do anything — see `docs/wake-word-training.md` in the source repo.
