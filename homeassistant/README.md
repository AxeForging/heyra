# Heyra — Home Assistant integration

Generated without a reachable HA instance from the dev session that wrote it
(see `CLAUDE.md` for why). Treat this as a strong draft, not a proven
deliverable, until you've run the checklist below.

## Before importing

1. **MQTT broker topology.** Heyra's `server/docker-compose.yml` runs its own
   dedicated mosquitto. For HA to see Heyra's MQTT Discovery entities, either:
   - point HA's MQTT integration at that broker (`<heyra-host>:1883`), or
   - point Heyra's `server/listener/config.yaml`'s `mqtt.host`/`mqtt.port` at
     your existing broker instead, and restart the `listener` container.
2. **Add the ESPHome integration** in HA for each unit (native API, not MQTT
   — uses the `api_encryption_key` from `firmware/secrets.yaml`). This is
   what creates `switch.*_streaming`, `binary_sensor.*_smoke_alarm_detected`,
   `binary_sensor.*_button`, `light.*_status_led`, and the
   `esphome.*_play_alert` service.
3. **Confirm entity IDs.** `automations.yaml`/`dashboard.yaml` assume HA
   slugifies `atom-echo-01` to `atom_echo_01` (its standard convention) —
   this was not verified against a live instance. Check your entity registry
   after step 2 and adjust the YAML if it differs.
4. **Telegram.** Nothing here is wired to a real bot. Set up HA's own
   `telegram_bot:` integration (see HA docs) and a corresponding `notify:`
   platform, then replace the placeholder `notify.telegram` service calls in
   `automations.yaml` with your actual service name.
5. **Notify targets for baby_cry/doorbell/dog_bark.** Replace the
   `notify.REPLACE_ME` placeholders with your actual `notify.mobile_app_*`
   (or similar) service.
6. **Quiet hours for baby_cry.** Create two `input_datetime` helpers,
   `input_datetime.quiet_hours_start` and `input_datetime.quiet_hours_end`
   (defaults assumed: 22:00 / 07:00 — edit to taste after creating them).
7. **Presence for glass_break.** The "nobody home" condition uses a generic
   template over all `person.*` entities — works with zero setup, but swap
   in your own zone/group entity if you have a more precise one.

## Manual test (once the above is done)

Mirrors the original spec's Phase 3 acceptance criteria:
1. Play a real smoke-alarm T3 pattern near a unit.
2. Within ~15s: a Telegram message should arrive, and the unit's speaker
   should beep while its LED strobes red.
3. Press any unit's button.
4. Tones stop, that unit's LED goes green for 5s, and a Telegram message
   "acked by `<room>`" arrives.

## Known-provisional pieces

- `distress_keyword` still runs on openWakeWord's stock placeholder model
  (Phase 2), not a trained "help help" model — the automation is wired
  correctly but will fire on stock-model phrases, not real distress speech,
  until that model is retrained.
- Only one unit (`atom-echo-01`, room `kitchen`) exists today. Adding a unit
  means adding its entity IDs to `automations.yaml`'s per-unit action lists
  and a new card to `dashboard.yaml` — both are intentionally manual, not
  templated (see `CLAUDE.md`'s "Unit count" note for why).
