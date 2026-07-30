# Changelog

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
