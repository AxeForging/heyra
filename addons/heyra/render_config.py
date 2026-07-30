"""Merges HA Add-on options (/data/options.json) and Supervisor-injected MQTT
service env vars (from config.yaml's `services: [mqtt:want]`) into the
checked-in listener/config.yaml template, writing the result to the path
listener.main actually reads.

Only `units` and the MQTT connection are exposed through the Add-on's
options UI -- per-event threshold/hysteresis tuning stays in a config.yaml
template, either the one baked into the image or, if present, a full
replacement dropped at the addon_config-mapped path (see DOCS.md). That's a
deliberate scope choice: exposing every event's tuning knob through the
auto-generated options UI would be a lot of schema surface for values that
are still provisional pending Phase 4 calibration anyway.
"""
from __future__ import annotations

import json
import os

import yaml

BAKED_IN_TEMPLATE_PATH = "/app/listener/config.yaml"
ADDON_CONFIG_OVERRIDE_PATH = "/config/config.yaml"  # addon_config map target, see config.yaml
OPTIONS_PATH = os.environ.get("HEYRA_OPTIONS", "/data/options.json")
OUTPUT_PATH = os.environ.get("HEYRA_CONFIG", "/app/config.yaml")


def render(template_path: str, options_path: str, env: dict) -> dict:
    with open(template_path) as f:
        config = yaml.safe_load(f)

    if os.path.exists(options_path):
        with open(options_path) as f:
            options = json.load(f)
        if options.get("units"):
            config["units"] = options["units"]

    mqtt_host = env.get("MQTT_HOST")
    if mqtt_host:
        config.setdefault("mqtt", {})
        config["mqtt"]["host"] = mqtt_host
        if env.get("MQTT_PORT"):
            config["mqtt"]["port"] = int(env["MQTT_PORT"])
        if env.get("MQTT_USERNAME"):
            config["mqtt"]["username"] = env["MQTT_USERNAME"]
        if env.get("MQTT_PASSWORD"):
            config["mqtt"]["password"] = env["MQTT_PASSWORD"]

    return config


def main() -> None:
    template_path = ADDON_CONFIG_OVERRIDE_PATH if os.path.exists(ADDON_CONFIG_OVERRIDE_PATH) else BAKED_IN_TEMPLATE_PATH
    config = render(template_path, OPTIONS_PATH, os.environ)
    with open(OUTPUT_PATH, "w") as f:
        yaml.safe_dump(config, f)


if __name__ == "__main__":
    main()
