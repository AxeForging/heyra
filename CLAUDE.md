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
  atom-echo-01 unit. Source of truth moved to `addons/heyra/` (see the AxeForging
  Add-ons entry below) — `cd server && docker compose up --build -d` still runs it locally
  for non-HA users (builds from `../addons/heyra`, own dedicated mosquitto, not
  shared with gjallarhorn).
  - 36/36 unit tests pass (`addons/heyra/listener/tests/` +
    `addons/heyra/test_render_config.py`, no hardware/Docker needed).
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
  `addons/heyra/listener/mqtt_out.py` actually expose; all 3 YAML files parse
  cleanly. See `homeassistant/README.md` for the setup checklist — note this file predates
  the AxeForging Add-ons below and its "no custom Add-on" reasoning has since been
  superseded; `addons/heyra` now covers the MQTT/config side natively.
- **AxeForging HA Add-on + hardware abstraction + public release** — built across two
  sessions, live-verified locally (not yet against a real Supervisor instance). **One**
  Add-on under `addons/heyra/` (originally built as two — `heyra-listener` +
  `heyra-flasher` — merged into one on the owner's explicit pushback: *"why 2 apps? Cant
  we have the flasher with the listener in a single add-on?"* `esphome` needs Python ≥3.12;
  rather than forking the base image, it gets its own venv at `/opt/esphome-venv`,
  provisioned via `uv` at build time — `esphome` only ever runs as a subprocess CLI
  (compile/upload), never imported as a library, so the interpreter mismatch doesn't
  matter. One process, `asyncio.gather()`: `addons/heyra/run.py` runs `listener.main.main()`
  (unchanged, owns its own healthz server) alongside the ingress uvicorn server. Verified
  live: `docker build addons/heyra` succeeds, a `docker run` with simulated Supervisor env
  vars (`INGRESS_PORT`, `/data/options.json`, `MQTT_HOST`) shows both the listener loop and
  ingress server starting in the same process, `/`, `/flash`, and `:8080/healthz` all
  respond correctly, and `/opt/esphome-venv/bin/esphome version` reports `2026.7.3` inside
  the running container), one repo (`repository.yaml` at root):
  - `addons/heyra/` — the Phase 2 service, packaged as a real Add-on. `options`/
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
  - **Flashing, merged into the same Add-on**: `addons/heyra/app/main.py` (Starlette,
    ingress-served on `/flash`) compiles/flashes Heyra firmware onto units over USB, instead
    of the `esphome` CLI from a dev machine. `uart: true` (mirrors the real ESPHome Add-on's
    own config, confirmed via direct fetch of `github.com/esphome/home-assistant-addon`):
    board dropdown (from `firmware/boards/`) → unit/WiFi form → shells `esphome compile`
    then `esphome upload` via the venv above, streams output live. Docker build context
    can't reach outside an Add-on's own folder, so `firmware/{common.yaml,boards/,
    components/}` are copied (not symlinked — symlinks escaping the build context aren't
    reliably followed) into `addons/heyra/firmware/` — **known duplication, keep in sync
    manually until a better build-context solution exists.**
  - `firmware/boards/` (Stage A prerequisite for the flasher's board dropdown), new `scream`
    event (Stage B), `help_en`/`socorro_pt` keyword scaffolding (Stage C) — see their own
    status lines above.
  - `repository.yaml`, root `README.md`, `LICENSE` (MIT), and the Add-on's `icon.png`/
    `logo.png` are done — icons rasterized from the real AxeForging brand kit
    (`~/workspace/axeforging/branding/logo.svg`/`wordmark.svg`) via ImageMagick, with a
    Heyra-specific accent color (`#ff3b3b`) substituted for the kit's default forge-orange,
    same "one custom accent per project" pattern as `rsvp-m5`'s own terracotta.
  - GitHub Pages landing site added: `web/index.html` (AxeForge brand kit + a Heyra-specific
    accent, `#ff3b3b`) deployed via `.github/workflows/pages.yml`, mirroring the real
    `AxeForging/rsvp-m5` Pages pattern (`configure-pages`/`upload-pages-artifact`/
    `deploy-pages`). Screenshot-verified locally before commit.
  - **Live**: `github.com/AxeForging/heyra` (public) and `https://axeforging.github.io/heyra/`
    (Pages, `build_type: workflow`, deployed successfully on first push, verified reachable
    with a real `curl`). Final secrets check re-run immediately before the push (clean, no
    real credentials ever committed, confirmed via `git log --all`).
  - **Real install attempted on the owner's actual HA instance — two real bugs found and
    fixed, not caught by any of the local Docker testing above:**
    1. Install hung/took a very long time — Supervisor was building the image from source
       on the owner's own (Pi-class) device, no `image:` key existed. Fixed: prebuilt
       multi-arch (`amd64`+`arm64`) image published to `ghcr.io/axeforging/heyra` via
       `.github/workflows/publish-addon.yml`, pattern confirmed against the real
       `esphome/esphome` release workflow (push-by-digest per arch on native ARM runners,
       `docker buildx imagetools create` to stitch the manifest). First run succeeded
       (`docker buildx imagetools inspect` confirmed both platforms) — **but the ghcr.io
       package published private by default; Supervisor needs unauthenticated pulls, so
       someone needs to flip it to Public at
       `github.com/orgs/AxeForging/packages/container/heyra/settings` before install will
       actually work** — flagged to the owner, not yet confirmed done.
    2. Ingress returned 502 even though the Add-on showed "Running" — confirmed via the
       owner's real log. Root cause: `host_network: true` + `ingress_port: 0` means
       Supervisor assigns a real port from its own dynamic range (62000-65500) and expects
       it fetched via `GET http://supervisor/addons/self/info` — `run.py` was binding to a
       hardcoded 8099 fallback instead (an invented `INGRESS_PORT` env var that doesn't
       exist). Fixed in `get_ingress_port()`, confirmed against the real ESPHome Add-on's
       own startup code. Added `hassio_api: true` for the token scope.
    - Also visible in that same real log: MQTT retrying forever against `mosquitto` (a
      hostname that only resolves in local `docker-compose`, not on a real HA instance) —
      not a code bug, but DOCS.md's "if you have a broker" aside was too easy to miss;
      now states plainly near the top that a real broker (recommended: the official
      Mosquitto Add-on, auto-discovered via `mqtt:want`) is required.
    - `logo.png` redesigned to actually say "Heyra" (was the generic AxeForge company
      wordmark, same file used everywhere else) — owner flagged this directly.
- **Ingress panel real-device fixes + flashing moved to WebSerial** — the owner tested the
  live Ingress panel after the 502 fix and found two more real bugs, then proposed (and
  this was built) moving flashing off the Add-on entirely:
  - **`/flash` was a real 404** — `STATUS_HTML`'s `href="/flash"` and the flash wizard's
    `fetch('/api/flash', ...)` were absolute paths, which drop HA Ingress's path prefix
    (`/api/hassio_ingress/<token>/...`) and resolve from the domain root instead. Fixed by
    making both relative (`0.3.1`) — since superseded by the flashing removal below.
  - **The flash form threw a real, silent 500** — `python-multipart` was never a declared
    dependency; Starlette raised in `await request.form()` before any board validation ran.
    Fixed in `0.3.2`, alongside surfacing configured units (room, online/offline, last
    packet) in the Ingress panel from `listener.healthz`'s own snapshot over loopback
    (`fetch_unit_snapshot()` in `app/main.py`) instead of only linking to an unproxied
    `:8080/healthz` URL — this is what "I cannot see the devices I already have" needed.
  - **Flashing moved to a WebSerial page** (`web/flash.html`, `esp-web-tools`), decided
    with the owner via `AskUserQuestion`: static IP → DHCP (dropped `manual_ip` from
    `common.yaml` entirely), and the Add-on flasher replaced outright (no redundant
    fallback). This required a real firmware redesign, not just moving a button — WebSerial
    needs one shared prebuilt binary, so nothing per-unit can be baked in at compile time
    anymore:
    - `esphome.name_add_mac_suffix: true` gives every physical unit a distinct hostname/AP
      name from one identical image — no more per-unit `device_name`/`friendly_name`/`room`
      substitutions (those were cosmetic HA-adoption naming only; the acoustic pipeline only
      ever cared about `unit_id`, which lives in the Add-on's own `options.units` config).
    - `unit_id` — the one value that must actually be set correctly per unit — is now a
      `restore_value` ESPHome `number:` entity (NVS-backed persistence, no custom C++
      storage) instead of a compile-time constant. Traced ESPHome's own source to confirm
      `restore_value` only republishes the *display* value on boot and does **not** fire
      `set_action` — `esphome.on_boot` pushes the restored value into
      `udp_audio_streamer`'s existing `set_unit_id()` setter; live changes (from HA or the
      device's own `web_server:` page) go through `set_action` instead.
    - Server discovery: `server_ip` → `server_host`, defaulting to `homeassistant.local`
      (resolved once via `getaddrinfo` in `setup()`, retried on an interval if the network
      isn't up yet) — `host_network: true` already puts the Add-on on the same IP HAOS's
      own avahi advertises that name for, so no new discovery mechanism was needed.
    - WiFi onboarding reuses `common.yaml`'s pre-existing `wifi.ap` fallback hotspot +
      `captive_portal:` (now open/passwordless, since there's no target network to protect
      it with on a generic image) — no new firmware component needed there either.
    - `api:`/`ota:` compile-time encryption/password dropped — confirmed by reading
      ESPHome's own source that both are compile-time-only with no runtime-generation
      mechanism, so a shared image genuinely can't carry a unique secret per unit. **Real
      security-posture change** (LAN-only trust boundary, same as ESPHome's own default
      when encryption isn't opted into) — flagged explicitly, not a silent downgrade.
    - `.github/workflows/pages.yml` now compiles `firmware/atom-echo.yaml` (the new
      canonical per-board build target, replacing the per-unit `firmware/units/*.yaml`
      pattern) and publishes `firmware.bin` + an `esp-web-tools` `manifest.json` into
      `web/firmware/atom-echo/` before the existing Pages upload step — not committed to
      git, built fresh each deploy. Verified live: real `curl` against the deployed
      `manifest.json` (correct fields, not just schema-shaped), `firmware.bin` (real
      ~1MB binary), and `flash.html` (200).
    - Add-on's `Dockerfile` drops the whole `esphome` + its own Python 3.12 `uv` venv layer
      and `uart: true` (no more USB passthrough) — verified via a real `docker build` +
      side-by-side size comparison against the published `0.3.2` image: **1.21GB → 750MB,
      ~38% smaller**, the concrete "make it lighter" the owner asked for.
  - **Not yet verified against real hardware** (flagged plainly, not assumed): the fallback
    AP actually appearing and being open, the captive portal actually accepting WiFi
    credentials on a secrets-free image, `homeassistant.local` actually resolving via mDNS
    from the firmware side, and the `unit_id` number entity actually surviving a reboot.
    Structural verification only (`esphome compile` succeeds clean, no warnings; addon test
    suite 48/48 passing) — real confirmation is the owner's, next time they flash a unit.
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

Not fixed. The owner has 4 physical units today. One shared firmware image now serves
every unit of a given board (see the WebSerial-flashing rework above) — adding a unit is
flashing another one via `web/flash.html` and adding an entry to the Add-on's `options.units`
config, no firmware-side per-unit file anymore.
