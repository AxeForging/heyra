"""Loads and resolves server/listener/config.yaml into typed, ready-to-use
structures. All override-merging happens here, once, at startup -- downstream
code (HysteresisGate, classify.py, keywords.py) never sees raw YAML.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from listener.hysteresis import EventRule


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class IngestConfig:
    bind_host: str
    port: int
    ring_seconds: float
    offline_timeout_s: float


@dataclass(frozen=True)
class HealthzConfig:
    port: int


@dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int
    discovery_prefix: str
    client_id: str


@dataclass(frozen=True)
class DebugConfig:
    enabled: bool
    output_dir: str
    rotate_seconds: float


@dataclass(frozen=True)
class EventConfig:
    """A fully-resolved event rule: hysteresis gate params plus everything
    needed to score and publish it. class_indices is empty for the keyword
    event (openWakeWord doesn't use YAMNet class scores)."""
    name: str
    threshold: float
    class_indices: tuple[int, ...]
    rule: EventRule
    diagnostics_only: bool
    off_delay_s: float


@dataclass(frozen=True)
class KeywordSpottingConfig:
    enabled: bool
    model_path: str
    inference_framework: str
    event: EventConfig


@dataclass(frozen=True)
class Config:
    ingest: IngestConfig
    healthz: HealthzConfig
    mqtt: MqttConfig
    debug: DebugConfig
    units: dict[int, str]  # unit_id -> room
    yamnet_model_path: str
    yamnet_class_map_path: str
    events: dict[str, EventConfig]  # YAMNet events, name -> config (defaults, pre-override)
    keyword_spotting: KeywordSpottingConfig
    gate_rules: dict[tuple[int, str], EventRule]  # (unit_id, event_name) -> resolved rule, post-override


def _require(d: dict, key: str, ctx: str):
    if key not in d:
        raise ConfigError(f"missing required key '{key}' in {ctx}")
    return d[key]


def _parse_event(name: str, raw: dict, ctx: str) -> EventConfig:
    threshold = _require(raw, "threshold", ctx)
    class_indices = tuple(raw.get("class_indices", ()))
    hyst = _require(raw, "hysteresis", ctx)
    rule = EventRule(
        hits=_require(hyst, "hits", f"{ctx}.hysteresis"),
        window_s=_require(hyst, "window_s", f"{ctx}.hysteresis"),
        cooldown_s=_require(raw, "cooldown_s", ctx),
    )
    ha = raw.get("ha", {})
    return EventConfig(
        name=name,
        threshold=threshold,
        class_indices=class_indices,
        rule=rule,
        diagnostics_only=bool(raw.get("diagnostics_only", False)),
        off_delay_s=float(ha.get("off_delay_s", 60)),
    )


def _apply_override(base: EventConfig, override: dict) -> EventConfig:
    threshold = override.get("threshold", base.threshold)
    hyst_override = override.get("hysteresis", {})
    rule = EventRule(
        hits=hyst_override.get("hits", base.rule.hits),
        window_s=hyst_override.get("window_s", base.rule.window_s),
        cooldown_s=override.get("cooldown_s", base.rule.cooldown_s),
    )
    return EventConfig(
        name=base.name,
        threshold=threshold,
        class_indices=base.class_indices,
        rule=rule,
        diagnostics_only=base.diagnostics_only,
        off_delay_s=override.get("ha", {}).get("off_delay_s", base.off_delay_s),
    )


def load_config(path: str) -> Config:
    with open(path) as f:
        raw = yaml.safe_load(f)

    ingest_raw = _require(raw, "ingest", "config")
    ingest = IngestConfig(
        bind_host=ingest_raw.get("bind_host", "0.0.0.0"),
        port=_require(ingest_raw, "port", "ingest"),
        ring_seconds=float(ingest_raw.get("ring_seconds", 2.0)),
        offline_timeout_s=float(ingest_raw.get("offline_timeout_s", 5.0)),
    )

    healthz_raw = raw.get("healthz", {})
    healthz = HealthzConfig(port=healthz_raw.get("port", 8080))

    mqtt_raw = _require(raw, "mqtt", "config")
    mqtt = MqttConfig(
        host=_require(mqtt_raw, "host", "mqtt"),
        port=int(mqtt_raw.get("port", 1883)),
        discovery_prefix=mqtt_raw.get("discovery_prefix", "homeassistant"),
        client_id=mqtt_raw.get("client_id", "heyra-listener"),
    )

    debug_raw = raw.get("debug", {})
    debug = DebugConfig(
        enabled=bool(debug_raw.get("enabled", False)),
        output_dir=debug_raw.get("output_dir", "/app/debug"),
        rotate_seconds=float(debug_raw.get("rotate_seconds", 30)),
    )

    units_raw = _require(raw, "units", "config")
    units: dict[int, str] = {}
    for entry in units_raw:
        unit_id = _require(entry, "unit_id", "units[]")
        room = _require(entry, "room", "units[]")
        units[unit_id] = room

    classify_raw = _require(raw, "classify", "config")
    yamnet_model_path = _require(classify_raw, "model_path", "classify")
    yamnet_class_map_path = _require(classify_raw, "class_map_path", "classify")
    events_raw = _require(classify_raw, "events", "classify")
    events = {
        name: _parse_event(name, ev_raw, f"classify.events.{name}")
        for name, ev_raw in events_raw.items()
    }

    kw_raw = _require(raw, "keyword_spotting", "config")
    kw_event = _parse_event("distress_keyword", kw_raw, "keyword_spotting")
    keyword_spotting = KeywordSpottingConfig(
        enabled=bool(kw_raw.get("enabled", True)),
        model_path=_require(kw_raw, "model_path", "keyword_spotting"),
        inference_framework=kw_raw.get("inference_framework", "tflite"),
        event=kw_event,
    )

    overrides_raw = raw.get("overrides") or {}
    gate_rules: dict[tuple[int, str], EventRule] = {}
    all_events = dict(events)
    all_events[keyword_spotting.event.name] = keyword_spotting.event
    for unit_id in units:
        unit_overrides = overrides_raw.get(unit_id, {})
        for name, base_cfg in all_events.items():
            resolved = _apply_override(base_cfg, unit_overrides.get(name, {}))
            gate_rules[(unit_id, name)] = resolved.rule
    for unit_id in overrides_raw:
        if unit_id not in units:
            raise ConfigError(f"overrides references unknown unit_id {unit_id}")

    return Config(
        ingest=ingest,
        healthz=healthz,
        mqtt=mqtt,
        debug=debug,
        units=units,
        yamnet_model_path=yamnet_model_path,
        yamnet_class_map_path=yamnet_class_map_path,
        events=events,
        keyword_spotting=keyword_spotting,
        gate_rules=gate_rules,
    )
