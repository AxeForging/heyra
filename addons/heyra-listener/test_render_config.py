"""Standalone test for render_config.py (not under listener/tests -- this
script isn't part of the listener package, it runs before it as the Add-on
entrypoint's config-generation step). Run with: pytest addons/heyra-listener/
"""
import json
import textwrap

from render_config import render


def test_render_applies_options_units_and_mqtt_env(tmp_path):
    template = tmp_path / "config.yaml"
    template.write_text(textwrap.dedent("""
        mqtt: {host: mosquitto, port: 1883}
        units:
          - {unit_id: 1, room: kitchen}
        classify: {model_path: /app/models/yamnet.tflite, class_map_path: /app/models/yamnet_class_map.csv, events: {}}
        keyword_spotting: []
    """))
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"units": [{"unit_id": 1, "room": "office"}, {"unit_id": 2, "room": "hallway"}]}))

    config = render(str(template), str(options), {
        "MQTT_HOST": "core-mosquitto",
        "MQTT_PORT": "8883",
        "MQTT_USERNAME": "heyra",
        "MQTT_PASSWORD": "secret",
    })

    assert config["units"] == [{"unit_id": 1, "room": "office"}, {"unit_id": 2, "room": "hallway"}]
    assert config["mqtt"] == {"host": "core-mosquitto", "port": 8883, "username": "heyra", "password": "secret"}


def test_render_without_options_file_or_mqtt_env_keeps_template(tmp_path):
    template = tmp_path / "config.yaml"
    template.write_text(textwrap.dedent("""
        mqtt: {host: mosquitto, port: 1883}
        units:
          - {unit_id: 1, room: kitchen}
        classify: {model_path: /app/models/yamnet.tflite, class_map_path: /app/models/yamnet_class_map.csv, events: {}}
        keyword_spotting: []
    """))
    missing_options = tmp_path / "does-not-exist.json"

    config = render(str(template), str(missing_options), {})

    assert config["units"] == [{"unit_id": 1, "room": "kitchen"}]
    assert config["mqtt"] == {"host": "mosquitto", "port": 1883}
