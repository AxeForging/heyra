import textwrap
from pathlib import Path

import pytest

from listener.config import ConfigError, load_config

REAL_CONFIG_PATH = Path(__file__).resolve().parents[2] / "listener" / "config.yaml"

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
  - event_name: distress_keyword
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


def test_keyword_spotting_list_parses_provisional_entries():
    # help_en/socorro_pt are provisional (no trained model file yet, see
    # config.yaml) but must still parse and get a gate rule -- they only get
    # skipped at spotter-startup (main.py) and discovery-publish (mqtt_out.py)
    # time, not at config-parse time.
    cfg = load_config(str(REAL_CONFIG_PATH))
    names = {kw.event.name for kw in cfg.keyword_spotting}
    assert names == {"distress_keyword", "help_en", "socorro_pt"}
    assert cfg.gate_rules[(1, "help_en")].hits == 2
    assert cfg.gate_rules[(1, "socorro_pt")].hits == 2


def test_scream_split_from_shout_in_real_config():
    # Regression guard for the shout/scream split: class index 11 ("Screaming")
    # must belong to scream only, not double-counted in shout.
    cfg = load_config(str(REAL_CONFIG_PATH))
    assert cfg.events["shout"].class_indices == (6, 9)
    assert cfg.events["scream"].class_indices == (11,)
    assert cfg.events["scream"].diagnostics_only is False


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
  - event_name: distress_keyword
    model_path: /app/models/openwakeword/hey_jarvis_v0.1.tflite
    threshold: 0.9
    hysteresis: {hits: 2, window_s: 10}
    cooldown_s: 60
"""
    path = write_yaml(tmp_path, text)
    with pytest.raises(ConfigError):
        load_config(path)
