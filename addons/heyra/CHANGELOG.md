# Changelog

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
