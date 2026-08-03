# Changelog

## 0.5.4

The Ingress panel now shows a recent-events log (last 200, in memory) with
filter (by event, by unit) and sort (newest/oldest/highest score) controls,
plus a "Raise alarm" button per event that re-publishes it through the same
MQTT pipeline a live detection uses. Units can now be renamed directly from
the panel instead of the Add-on's Configuration tab, where `room` was
effectively hidden -- renaming unpublishes the old room's MQTT discovery
entities first (so HA doesn't accumulate stale/unavailable ones), writes the
new room via the Supervisor options API, then restarts the Add-on (room is
read once at listener startup, not hot-reloaded).

## 0.5.3

Retheme to the AxeForge kit's `relay` flavor (external tools/hardware/browser
extensions -- shared with sibling projects rsvp-m5 and ReplayRaccoon), replacing
the one-off `#ff3b3b` accent that lived outside the kit's sanctioned mechanism.
Ingress panel, landing page, flash page, and Store card art (icon.png/logo.png)
all move to the new `#ff6b00` accent + neutral-gray shell.

## 0.5.2

Fixes a real bug on Assign: same class as the 0.3.1 `/flash` 404 -- the
`/assign` route's redirect used an absolute `"/"` `Location` header, which
drops HA Ingress's path prefix. After hitting Assign, the panel's own
iframe navigated to the domain root and re-loaded the whole HA frontend
(sidebar included) inside itself, worse on every refresh since each one
nested another copy. Redirect is now relative to the request.

## 0.5.1

Redesigned the Ingress panel -- real visual hierarchy (a proper primary
action for flashing, status pills instead of a bare dot, panels with real
depth) instead of three visually-identical flat cards, per this project's
own Impeccable design context. Also fixes the Add-on Store's Info tab: the
description card still said "USB firmware flashing" (removed in `0.4.0`)
and never listed what Heyra actually detects; `config.yaml`'s description
no longer collides with Supervisor's own appended "Visit Heyra page for
more details" sentence into a visible double period.

## 0.5.0

The Add-on is now the one place to set a unit's ID -- no more separately
visiting the device's own local page and hoping the two stay in sync. The
Ingress panel discovers Heyra units on the network via mDNS
(`_esphomelib._tcp.local.`, the same mechanism ESPHome's own dashboard uses)
and shows each one's currently-reported Unit ID; picking a configured unit
and hitting Assign pushes it directly through the device's `web_server:`
HTTP API (`POST /number/unit_id_number/set`), which applies and persists
immediately. New `zeroconf` dependency for the mDNS browsing.

## 0.4.0

Flashing moves off the Add-on entirely, onto
[axeforging.github.io/heyra/flash.html](https://axeforging.github.io/heyra/flash.html)
(WebSerial, runs in the browser, no dev machine needed) -- it now works
from whatever laptop or phone you're holding, not just whatever machine
runs Home Assistant itself (previously flashing needed the ATOM Echo
plugged in over USB to that specific machine). This also drops the
Add-on's single largest layer: no more esphome or its own Python 3.12
venv, no more `uart: true` USB passthrough. The Ingress panel is now a
device-status view only (see 0.3.2's device list) with a link out to the
flashing page. See firmware's own changes for what made a single shared
image possible (runtime Unit ID, DHCP, mDNS server discovery).

## 0.3.2

Fixes a real 500 on the flash form: `python-multipart` was never a declared
dependency, so Starlette raised before any board validation ran the moment
the browser submitted the (multipart/form-data) flash form -- exactly the
bare "Internal Server Error" some users saw. The Ingress panel now also
shows your actually-configured units (room, online/offline, last packet
seen) pulled from the listener's own `/healthz` snapshot over loopback,
instead of only linking out to a separate, unproxied URL. The flash form's
Unit ID field is now pre-filled with the next unused ID instead of a
placeholder that looked like a real default; the static-IP/device-name
placeholders are now clearly marked as examples.

## 0.3.1

Fixes a real 404 on "Flash a unit": the Ingress panel's `href="/flash"` and the
flash wizard's `fetch('/api/flash', ...)` were absolute paths, which drop HA
Ingress's path prefix (`/api/hassio_ingress/<token>/...`) and resolve from the
domain root instead. Now relative. Also restyled both Ingress pages (dark
background, Heyra's real `#ff3b3b` accent, Inter/JetBrains Mono) -- they were
still on plain light/system styling with a stale accent color left over from
before the brand was finalized.

## 0.3.0

Fixes a real 502 on Ingress: with `host_network: true` + `ingress_port: 0`,
Supervisor assigns a real port from its own dynamic range (62000-65500) and
expects it fetched via the Supervisor API -- there's no env var carrying it.
`run.py` was binding to a hardcoded fallback (8099) instead, so the ingress
proxy had nothing listening on the port it actually expected. Added
`hassio_api: true` so the Supervisor API call has the needed scope. Also
made the MQTT broker requirement explicit in DOCS.md (was silently failing
with `mqtt connection error` in the log otherwise) and ships as a prebuilt
multi-arch image (`ghcr.io/axeforging/heyra`) instead of building from
source on-device -- installs were hanging/very slow on Pi-class hardware
compiling numpy/scipy/tflite-runtime/onnxruntime/esphome from scratch.

## 0.2.0

Merged the separate `heyra-flasher` Add-on into this one -- one Add-on
install instead of two. Adds a USB firmware-flashing wizard (board picker,
unit/WiFi form, live `esphome compile`/`upload` log streaming) to the
Ingress panel, alongside the existing listener service. `esphome` runs
from its own Python 3.12 venv inside the same image (provisioned via
`uv`), invoked as a subprocess -- doesn't touch the listener's proven
numpy/tflite-runtime stack.

## 0.1.0

Initial release. YAMNet event detection (baby cry, smoke alarm, glass
break, dog bark, doorbell, shout, scream), openWakeWord keyword spotting
(stock placeholder `distress_keyword`, provisional `help_en`/`socorro_pt`
slots pending trained models), MQTT Discovery, `mqtt:want` broker
auto-discovery.
