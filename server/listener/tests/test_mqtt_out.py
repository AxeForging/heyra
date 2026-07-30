import textwrap
from pathlib import Path

import pytest

from listener.config import load_config
from listener.mqtt_out import MqttPublisher

# A real file on disk to stand in for "model present" -- model_path values in
# the real config.yaml are container-absolute (/app/models/...), which never
# resolve on the host these tests run on, so this test builds its own config
# with a host-resolvable path instead of loading config.yaml directly.
REAL_MODEL_FILE = Path(__file__).resolve().parents[2] / "models" / "openwakeword" / "hey_jarvis_v0.1.tflite"


class _FakeMqttClient:
    def __init__(self):
        self.published_topics: list[str] = []

    async def publish(self, topic, payload, retain=False):
        self.published_topics.append(topic)


@pytest.mark.asyncio
async def test_discovery_skips_keyword_events_with_missing_model(tmp_path):
    assert REAL_MODEL_FILE.exists(), "fixture assumption: stock hey_jarvis model ships in the repo"
    config_yaml = tmp_path / "config.yaml"
    config_yaml.write_text(textwrap.dedent(f"""
        ingest: {{port: 6969}}
        mqtt: {{host: mosquitto}}
        units:
          - {{unit_id: 1, room: kitchen}}
        classify:
          model_path: /app/models/yamnet.tflite
          class_map_path: /app/models/yamnet_class_map.csv
          events:
            doorbell: {{class_indices: [349, 350], threshold: 0.45, hysteresis: {{hits: 1, window_s: 1}}, cooldown_s: 60}}
        keyword_spotting:
          - event_name: distress_keyword
            model_path: {REAL_MODEL_FILE}
            threshold: 0.9
            hysteresis: {{hits: 2, window_s: 10}}
            cooldown_s: 60
          - event_name: help_en
            model_path: /definitely/does/not/exist/help_en.tflite
            threshold: 0.9
            hysteresis: {{hits: 2, window_s: 10}}
            cooldown_s: 60
    """))
    config = load_config(str(config_yaml))
    publisher = MqttPublisher("mosquitto", 1883, "test-client", "homeassistant")
    fake_client = _FakeMqttClient()
    publisher._client = fake_client

    await publisher.publish_all_discovery(config)

    published = " ".join(fake_client.published_topics)
    assert "heyra_kitchen_distress_keyword" in published
    assert "heyra_kitchen_doorbell" in published
    assert "heyra_kitchen_help_en" not in published
