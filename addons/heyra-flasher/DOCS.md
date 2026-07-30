# Heyra Flasher

Open the panel (sidebar icon), plug an ATOM Echo (or other supported board)
into this machine over USB, pick the board and fill in the unit details,
hit Flash. Streams the real `esphome compile`/`esphome upload` output live.

## Requirements

- `uart: true` — this Add-on needs USB-serial access, granted automatically.
  If your device doesn't show up in the port list, unplug/replug it and
  reload the page.
- WiFi credentials and unit details (room, device name, unit ID, static IP)
  are entered per-flash through the form — nothing is stored between runs.

## Compatible hardware

Same list as the main firmware — see `firmware/boards/README.md` in the
[source repo](https://github.com/AxeForging/heyra). Only boards with a
`boards/<name>.yaml` profile show up in the dropdown.

## What this doesn't do

- No OTA flashing yet (USB only) — a unit already on your network can still
  be re-flashed with the `esphome` CLI directly, or via the official
  ESPHome Add-on if you have it installed.
- No log tailing after flashing — add the ESPHome integration in Home
  Assistant (Settings → Devices & Services) to see a flashed unit's logs
  and entities.
