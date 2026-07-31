# Heyra

Detects these by sound and tells Home Assistant: baby crying, a smoke alarm
(also runs on-device, so it keeps working if the server or network goes
down), glass breaking, a dog barking, a doorbell, shouting, and screaming —
plus two provisional wake-word slots. Under the hood: YAMNet + openWakeWord
classification, published via MQTT Discovery.

New units are flashed straight from your browser (WebSerial, no dev machine)
and assigned to a room right here in this panel, via mDNS discovery — no
separate device page to keep in sync.

By [AxeForging](https://github.com/AxeForging), for
[Heyra](https://github.com/AxeForging/heyra).

See [`DOCS.md`](./DOCS.md) for configuration, or the main
[Heyra README](../../README.md) for the full project.
