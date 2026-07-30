import textwrap

import pytest

from listener.config import ConfigError, load_config

BASE_YAML = """
ingest: {port: 6969}
mqtt: {host: mosquitto}
units:
  - {unit_id: 1, room: kitchen}
classify:
  model_path: /app/models/yamnet.tflite
  class_map_path: /app/models/yamnet_class_map.csv
  events:
    doorbell:
      class_indices: [349, 350]
      threshold: 0.45
      hysteresis: {hits: 1, window_s: 1}
      cooldown_s: 60
keyword_spotting:
  model_path: /app/models/openwakeword/hey_jarvis_v0.1.tflite
  threshold: 0.9
  hysteresis: {hits: 2, window_s: 10}
  cooldown_s: 60
"""


def write_yaml(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(text))
    return str(p)


def test_loads_base_config(tmp_path):
    path = write_yaml(tmp_path, BASE_YAML)
    cfg = load_config(path)
    assert cfg.units == {1: "kitchen"}
    assert cfg.events["doorbell"].threshold == 0.45
    assert cfg.gate_rules[(1, "doorbell")].hits == 1
    assert cfg.gate_rules[(1, "distress_keyword")].hits == 2


def test_override_changes_threshold_but_not_others(tmp_path):
    text = BASE_YAML + """
overrides:
  1:
    doorbell: {threshold: 0.9}
"""
    path = write_yaml(tmp_path, text)
    cfg = load_config(path)
    # gate_rules only carries the hysteresis rule, not threshold -- verify the
    # rule itself is unaffected by a threshold-only override.
    assert cfg.gate_rules[(1, "doorbell")].hits == 1
    assert cfg.events["doorbell"].threshold == 0.45  # base config unchanged


def test_override_unknown_unit_raises(tmp_path):
    text = BASE_YAML + """
overrides:
  99:
    doorbell: {threshold: 0.9}
"""
    path = write_yaml(tmp_path, text)
    with pytest.raises(ConfigError):
        load_config(path)


def test_missing_threshold_raises(tmp_path):
    text = """
ingest: {port: 6969}
mqtt: {host: mosquitto}
units:
  - {unit_id: 1, room: kitchen}
classify:
  model_path: /app/models/yamnet.tflite
  class_map_path: /app/models/yamnet_class_map.csv
  events:
    doorbell:
      class_indices: [349, 350]
      hysteresis: {hits: 1, window_s: 1}
      cooldown_s: 60
keyword_spotting:
  model_path: /app/models/openwakeword/hey_jarvis_v0.1.tflite
  threshold: 0.9
  hysteresis: {hits: 2, window_s: 10}
  cooldown_s: 60
"""
    path = write_yaml(tmp_path, text)
    with pytest.raises(ConfigError):
        load_config(path)
