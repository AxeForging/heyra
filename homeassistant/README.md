# Heyra — Home Assistant integration

Live-checked against the real instance at `http://homeassistant.local:8123/`
(HA 2026.7.3, Home Assistant OS/Supervised) via a Long-Lived Access Token.
Confirmed: `hassio` present (Add-on Store available), `esphome` absent (not
added yet), `mqtt` present but pointed at a different broker than Heyra's,
`telegram_bot` absent, `mobile_app` present with 3 registered devices. The
checklist below reflects those findings, not guesses.

## Before importing

1. **MQTT broker topology.** HA already has its own MQTT integration
   connected to some broker — Heyra's dedicated `server/mosquitto` container
   isn't it. Recommended: point Heyra's `server/listener/config.yaml`'s
   `mqtt.host`/`mqtt.port` at HA's existing broker instead (find its address
   under Settings → Devices & Services → MQTT → Configure), then restart the
   `listener` container. This supersedes the earlier "Heyra gets its own
   mosquitto" plan — simpler than running two brokers and bridging them. If
   you'd rather keep Heyra's bundled mosquitto standalone, that still works,
   you'll just need a bridge config between the two brokers instead.
2. **Add the ESPHome integration** in HA for each unit (native API, not MQTT
   — uses the `api_encryption_key` from `firmware/secrets.yaml`). Confirmed
   not yet added as of this check. This is what creates
   `switch.*_streaming`, `binary_sensor.*_smoke_alarm_detected`,
   `binary_sensor.*_button`, `light.*_status_led`, and the
   `esphome.*_play_alert` service.
3. **Confirm entity IDs.** `automations.yaml`/`dashboard.yaml` assume HA
   slugifies `atom-echo-01` to `atom_echo_01` (its standard convention) —
   couldn't verify this live since the ESPHome integration isn't added yet.
   Check your entity registry after step 2 and adjust the YAML if it
   differs.
4. **Notifications.** `automations.yaml` calls `notify.notify`, HA's
   built-in group service — it broadcasts to every registered notify target
   (currently `mobile_app_np2`, `mobile_app_iphone`,
   `mobile_app_iphone_de_carol`). No Telegram bot needed. Want per-person
   routing on a specific automation instead of broadcasting to everyone?
   Swap that automation's `notify.notify` for e.g. `notify.mobile_app_np2`.
5. **Quiet hours for baby_cry.** Create two `input_datetime` helpers,
   `input_datetime.quiet_hours_start` and `input_datetime.quiet_hours_end`
   (defaults assumed: 22:00 / 07:00 — edit to taste after creating them).
6. **Presence for glass_break.** The "nobody home" condition uses a generic
   template over all `person.*` entities — works with zero setup, but swap
   in your own zone/group entity if you have a more precise one.

## Optional: Add-ons

Two "install as a plugin" ideas came up. Verdict on each:

- **Packaging Heyra's listener (`server/`) as a custom HA Add-on** — not
  done, and not recommended. MQTT Discovery (already built into Phase 2)
  already auto-creates every entity in HA with zero manual config, which is
  the actual benefit an Add-on would buy. Wrapping it as a formal Add-on
  would only save you one `docker compose up` command at the cost of
  maintaining an Add-on `config.yaml`/repo listing — not worth it here.
  Keep running it via `server/docker-compose.yml`.
- **Flashing/configuring units from within HA** — use the official
  **ESPHome Add-on** (built by the ESPHome project, install from Settings →
  Add-ons → Add-on Store). It's a full web dashboard for creating,
  compiling, and flashing ESPHome device configs over USB or OTA. Import
  `firmware/common.yaml` and `firmware/units/*.yaml` into it if you'd
  rather manage the fleet from HA's UI instead of the `esphome` CLI from a
  dev machine. Not required — CLI flashing still works exactly as before.

## Manual test (once the above is done)

Mirrors the original spec's Phase 3 acceptance criteria:
1. Play a real smoke-alarm T3 pattern near a unit.
2. Within ~15s: a notification should arrive on your registered phones, and
   the unit's speaker should beep while its LED strobes red.
3. Press any unit's button.
4. Tones stop, that unit's LED goes green for 5s, and a notification
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
