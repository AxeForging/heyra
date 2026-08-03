"""Ingress web UI: shows configured units and their live status, and lets you assign a
discovered device's unit_id directly -- one place to set it, not two (the Add-on's own
options.units config and a separate visit to the device's own local page).

Flashing moved to the public WebSerial page (axeforging.github.io/heyra/flash.html) --
one shared firmware image, no per-unit compile, so there's no reason for it to run here
anymore. This app is now just a thin status view over listener.healthz's snapshot, plus
the discovery/assignment feature below.
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiomqtt
import requests
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from app.discovery import discovery
from listener.config import load_config
from listener.mqtt_out import discovery_topics_for_room

# Same config.yaml hit_consumer_loop/publish_all_discovery read (listener.main.CONFIG_PATH
# isn't imported directly -- that module also imports the full YAMNet/tflite ML stack,
# which this ingress app has no other reason to load).
CONFIG_PATH = os.environ.get("HEYRA_CONFIG", "/app/config.yaml")
SUPERVISOR_URL = "http://supervisor"


@asynccontextmanager
async def lifespan(app):
    await discovery.start()
    try:
        yield
    finally:
        await discovery.stop()

# listener.healthz binds this in the same container/process (see run.py) -- loopback,
# not proxied through Ingress, so this call never leaves the container.
HEALTHZ_URL = "http://127.0.0.1:8080/healthz"
FLASH_URL = "https://axeforging.github.io/heyra/flash.html"


def fetch_unit_snapshot() -> dict:
    # Same-container loopback call to listener.healthz (see run.py -- both run in one
    # process). Swallow failures -- the listener may still be starting up, or this call
    # races its own server binding -- the page should render "starting up", not crash.
    try:
        resp = requests.get(HEALTHZ_URL, timeout=2)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def sanitize_room(raw: str) -> str:
    """Lowercase, [a-z0-9_] only -- a room name flows straight into an MQTT topic
    segment (acoustic/{room}/event) and an HA entity unique_id (heyra_{room}_{event}),
    same alphabet every room name in this repo already uses (kitchen, living_room)."""
    return re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_")


def _supervisor_headers() -> dict[str, str] | None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


async def _mqtt_publish_once(topic_payloads: list[tuple[str, str | bytes, bool]]) -> None:
    """Opens a short-lived MQTT connection, publishes each (topic, payload, retain),
    closes. Best-effort -- callers already treat MQTT unavailability as non-fatal, same
    as /assign's own device-unreachable handling."""
    config = load_config(CONFIG_PATH)
    async with aiomqtt.Client(
        config.mqtt.host, config.mqtt.port,
        username=config.mqtt.username, password=config.mqtt.password,
    ) as client:
        for topic, payload, retain in topic_payloads:
            await client.publish(topic, payload, retain=retain)


def filter_sort_events(events: list[dict], event_filter: str, unit_filter: str, order: str) -> list[dict]:
    filtered = events
    if event_filter and event_filter != "all":
        filtered = [e for e in filtered if e["event"] == event_filter]
    if unit_filter and unit_filter != "all":
        filtered = [e for e in filtered if str(e["unit_id"]) == unit_filter]
    if order == "oldest":
        return sorted(filtered, key=lambda e: e["ts"])
    if order == "score":
        return sorted(filtered, key=lambda e: e["score"], reverse=True)
    return sorted(filtered, key=lambda e: e["ts"], reverse=True)  # "newest", also the default


def render_events_html(events: list[dict], units: dict, query: dict) -> str:
    selected_event = query.get("event", "all")
    selected_unit = query.get("unit", "all")
    selected_order = query.get("order", "newest")

    event_names = sorted({e["event"] for e in events})
    event_options = '<option value="all">All events</option>' + "".join(
        f'<option value="{html.escape(n)}"{" selected" if n == selected_event else ""}>{html.escape(n)}</option>'
        for n in event_names
    )
    unit_options = '<option value="all">All units</option>' + "".join(
        f'<option value="{html.escape(uid)}"{" selected" if uid == selected_unit else ""}>'
        f'{html.escape(str(u.get("room", uid)))}</option>'
        for uid, u in sorted(units.items(), key=lambda kv: int(kv[0]))
    )
    order_options = "".join(
        f'<option value="{val}"{" selected" if val == selected_order else ""}>{label}</option>'
        for val, label in (("newest", "Newest first"), ("oldest", "Oldest first"), ("score", "Highest score"))
    )
    form = (
        '<form method="get" class="filter-form">'
        f'<select name="event">{event_options}</select>'
        f'<select name="unit">{unit_options}</select>'
        f'<select name="order">{order_options}</select>'
        '<button type="submit">Apply</button>'
        "</form>"
    )

    filtered = filter_sort_events(events, selected_event, selected_unit, selected_order)
    if not filtered:
        note = "No events yet" if not events else "No events match this filter"
        return form + f'<div class="empty-note">{note} -- once a detector fires, it shows up here.</div>'

    rows = []
    for e in filtered:
        when = datetime.fromtimestamp(e["ts"], tz=timezone.utc).strftime("%H:%M:%S")
        rows.append(
            '<div class="row">'
            '<div class="row-main">'
            f'<div class="room-name">{html.escape(str(e["event"]))}</div>'
            f'<div class="row-meta">{html.escape(str(e.get("room", "?")))} &middot; {when} UTC '
            f'&middot; score {e["score"]:.2f}</div>'
            "</div>"
            '<form method="post" action="reraise" class="assign-form">'
            f'<input type="hidden" name="unit_id" value="{html.escape(str(e["unit_id"]))}">'
            f'<input type="hidden" name="event" value="{html.escape(str(e["event"]))}">'
            f'<input type="hidden" name="score" value="{e["score"]}">'
            '<button type="submit">Raise alarm</button>'
            "</form>"
            "</div>"
        )
    return form + '<div class="panel">' + "".join(rows) + "</div>"


def next_unit_id(units: dict) -> int:
    used = {int(uid) for uid in units}
    candidate = 1
    while candidate in used:
        candidate += 1
    return candidate


def render_units_html(units: dict) -> str:
    if not units:
        return '<div class="empty-note">No units configured yet, or the listener is still starting up.</div>'
    rows = []
    for unit_id in sorted(units, key=int):
        u = units[unit_id]
        status = "online" if u.get("online") else "offline"
        age = u.get("last_packet_age_s")
        age_text = f"{age:.0f}s ago" if age is not None else "never"
        rows.append(
            '<div class="row">'
            f'<span class="pill pill-{status}">{status}</span>'
            '<div class="row-main">'
            f'<div class="room-name">{html.escape(str(u.get("room", "?")))}</div>'
            f'<div class="row-meta">unit {html.escape(str(unit_id))} &middot; last packet {age_text}</div>'
            "</div>"
            '<form method="post" action="rename" class="assign-form">'
            f'<input type="hidden" name="unit_id" value="{html.escape(str(unit_id))}">'
            f'<input type="text" name="room" value="{html.escape(str(u.get("room", "")))}" '
            'class="rename-input" placeholder="room name">'
            '<button type="submit">Rename</button>'
            "</form>"
            "</div>"
        )
    return "".join(rows)


def fetch_device_unit_id(hostname: str) -> int | None:
    # Same web_server: HTTP API the /assign route below writes through -- a device
    # mid-boot or just-flashed-and-not-yet-networked shouldn't break the page.
    try:
        resp = requests.get(f"http://{hostname}/number/unit_id_number", timeout=3)
        resp.raise_for_status()
        return int(float(resp.json()["value"]))
    except Exception:
        return None


async def render_discovered_html(devices: dict, configured_unit_ids: list[int]) -> str:
    if not devices:
        return (
            '<div class="empty-note">No unclaimed devices found yet. Flash one above, connect it '
            "to your Wi-Fi, and it'll show up here.</div>"
        )
    hostnames = sorted(devices)
    current_ids = await asyncio.gather(*(run_in_threadpool(fetch_device_unit_id, h) for h in hostnames))
    options = "".join(f'<option value="{uid}">{uid}</option>' for uid in configured_unit_ids)
    rows = []
    for hostname, current_id in zip(hostnames, current_ids):
        current_text = f"currently reports unit {current_id}" if current_id is not None else "not reachable yet"
        rows.append(
            '<div class="row">'
            '<div class="row-main">'
            f'<div class="hostname">{html.escape(hostname)}</div>'
            f'<div class="row-meta">{current_text}</div>'
            "</div>"
            '<form method="post" action="assign" class="assign-form">'
            f'<input type="hidden" name="hostname" value="{html.escape(hostname)}">'
            f'<label class="assign-label">Unit <select name="unit_id">{options}</select></label>'
            '<button type="submit">Assign</button>'
            "</form>"
            "</div>"
        )
    return "".join(rows)


async def index(request):
    snapshot = await run_in_threadpool(fetch_unit_snapshot)
    units = snapshot.get("units", {})
    events = snapshot.get("events", [])
    discovered_html = await render_discovered_html(dict(discovery.devices), sorted(int(u) for u in units))
    return HTMLResponse(STATUS_HTML.format(
        units_html=render_units_html(units),
        events_html=render_events_html(events, units, request.query_params),
        discovered_html=discovered_html,
        next_unit_id=next_unit_id(units),
        flash_url=FLASH_URL,
    ))


async def assign(request):
    form = await request.form()
    hostname = form.get("hostname", "")
    unit_id = form.get("unit_id", "")
    if hostname and unit_id:
        try:
            requests.post(f"http://{hostname}/number/unit_id_number/set", params={"value": unit_id}, timeout=5)
        except Exception:
            pass  # best-effort -- the device list will just keep showing its prior state
    # Relative, not "/" -- an absolute path drops HA Ingress's path prefix and navigates
    # the panel's iframe to the domain root, which re-loads the whole HA frontend (sidebar
    # included) inside itself. Same class of bug already fixed for /flash, see bd4a684.
    return RedirectResponse(url=".", status_code=303)


async def reraise(request):
    """Re-publishes a past event's MQTT payload with a fresh timestamp -- fires
    whatever HA automation is already wired to it. Not the physical play_alert tone:
    that's an ESPHome api: action, only callable via a Home Assistant service call,
    and the ESPHome integration isn't set up yet (see CLAUDE.md)."""
    form = await request.form()
    unit_id = form.get("unit_id", "")
    event_name = form.get("event", "")
    score = form.get("score", "")
    room = None
    if unit_id and event_name:
        snapshot = await run_in_threadpool(fetch_unit_snapshot)
        unit = snapshot.get("units", {}).get(unit_id)
        room = unit.get("room") if unit else None
    if room:
        try:
            payload = json.dumps({
                "event": event_name,
                "score": float(score) if score else 0.0,
                "unit_id": int(unit_id),
                "ts": time.time(),
            })
            await _mqtt_publish_once([(f"acoustic/{room}/event", payload, False)])
        except Exception:
            pass  # best-effort, mirrors /assign's own error handling
    return RedirectResponse(url=".", status_code=303)


async def rename(request):
    """Renames a unit's room from the panel instead of the Add-on's Configuration tab.
    Unpublishes the old room's MQTT discovery entities first (so they don't linger as
    unavailable in HA), writes the new room via the Supervisor API, then restarts the
    Add-on -- room is read once at listener startup, not hot-reloaded."""
    form = await request.form()
    unit_id_raw = form.get("unit_id", "")
    new_room = sanitize_room(form.get("room", ""))
    headers = _supervisor_headers()

    if unit_id_raw and new_room and headers is not None:
        try:
            info_resp = await run_in_threadpool(
                lambda: requests.get(f"{SUPERVISOR_URL}/addons/self/info", headers=headers, timeout=5)
            )
            info_resp.raise_for_status()
            options = info_resp.json()["data"]["options"]
            unit_entries = options.get("units", [])
            target = next((u for u in unit_entries if str(u.get("unit_id")) == str(unit_id_raw)), None)
            other_rooms = {u.get("room") for u in unit_entries if u is not target}

            if target is not None and target.get("room") != new_room and new_room not in other_rooms:
                old_room = target["room"]
                try:
                    config = load_config(CONFIG_PATH)
                    topics = discovery_topics_for_room(config, old_room)
                    await _mqtt_publish_once([(t, b"", True) for t in topics])
                except Exception:
                    pass  # best-effort -- still proceed with the rename itself

                target["room"] = new_room
                await run_in_threadpool(
                    lambda: requests.post(
                        f"{SUPERVISOR_URL}/addons/self/options", headers=headers,
                        json={"options": options}, timeout=10,
                    )
                )

                async def _restart_soon():
                    # Give this response time to actually flush to the browser before
                    # the container (and this uvicorn process) restarts.
                    await asyncio.sleep(1)
                    try:
                        await run_in_threadpool(
                            lambda: requests.post(f"{SUPERVISOR_URL}/addons/self/restart", headers=headers, timeout=10)
                        )
                    except Exception:
                        pass

                asyncio.create_task(_restart_soon())
        except Exception:
            pass  # best-effort -- collision/unreachable-Supervisor cases just no-op
    return RedirectResponse(url=".", status_code=303)


STATUS_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Heyra</title>
<style>
  :root {{
    --bg: #0a0a0a; --surface: #1a1a1a; --line: #2a2a2a;
    --text: #ffffff; --text-muted: #94a3b8;
    --accent: #ff6b00; --accent-hover: #e56000; --accent-contrast: #05070a;
    --online-bg: rgba(34, 197, 94, 0.14); --online-text: #4ade80;
    --offline-bg: rgba(148, 163, 184, 0.1); --offline-text: #94a3b8;
    --radius: 0.6rem;
    --mono: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Inter", ui-sans-serif, system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    max-width: 640px; margin: 0 auto; padding: 3rem 1.25rem 4rem;
  }}
  .kicker {{
    font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--accent); margin-bottom: 0.6rem;
  }}
  h1 {{ font-size: 1.9rem; font-weight: 700; letter-spacing: -0.02em; margin: 0 0 0.4rem; }}
  .lede {{ color: var(--text-muted); margin: 0 0 2.25rem; line-height: 1.5; }}

  .primary-action {{
    display: block; text-decoration: none; color: var(--accent-contrast);
    background: var(--accent); border-radius: var(--radius);
    padding: 1.1rem 1.35rem;
    box-shadow: 0 16px 32px -18px rgba(255, 107, 0, 0.45);
    transition: background 0.15s ease, transform 0.1s ease;
  }}
  .primary-action:hover {{ background: var(--accent-hover); }}
  .primary-action:active {{ transform: scale(0.99); }}
  .primary-action strong {{ display: block; font-size: 1.05rem; margin-bottom: 0.2rem; }}
  .primary-action span {{ color: color-mix(in srgb, var(--accent-contrast) 85%, transparent); font-size: 0.85rem; }}

  section {{ margin-top: 2.5rem; }}
  .kicker-sm {{
    font-family: var(--mono); font-size: 0.72rem; font-weight: 400; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--text-muted); margin: 0 0 0.85rem;
  }}
  .panel {{
    background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
    box-shadow: 0 24px 48px -32px rgba(0, 0, 0, 0.6);
    overflow: hidden;
  }}
  .empty-note {{ padding: 1.1rem 1.25rem; color: var(--text-muted); font-size: 0.9rem; }}

  .row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 0.85rem; padding: 0.9rem 1.25rem; }}
  .row + .row {{ border-top: 1px solid var(--line); }}
  .row-main {{ flex: 1; min-width: 0; }}
  .room-name {{ font-weight: 600; }}
  .hostname {{ font-family: var(--mono); font-size: 0.88rem; }}
  .row-meta {{ color: var(--text-muted); font-size: 0.82rem; margin-top: 0.15rem; }}

  .pill {{
    flex: none; font-family: var(--mono); font-size: 0.68rem; letter-spacing: 0.04em;
    text-transform: uppercase; font-weight: 600; padding: 0.22rem 0.55rem; border-radius: 999px;
  }}
  .pill-online {{ background: var(--online-bg); color: var(--online-text); }}
  .pill-offline {{ background: var(--offline-bg); color: var(--offline-text); }}

  .assign-form {{ display: flex; align-items: center; gap: 0.5rem; flex: none; }}
  .assign-label {{ font-size: 0.78rem; color: var(--text-muted); display: flex; align-items: center; gap: 0.35rem; }}
  .assign-form select {{
    background: var(--bg); color: var(--text); border: 1px solid var(--line);
    border-radius: 0.35rem; padding: 0.3rem 0.5rem; font-size: 0.85rem;
  }}
  .assign-form button {{
    background: var(--accent); color: var(--accent-contrast); border: none; border-radius: 0.35rem;
    padding: 0.35rem 0.7rem; font-size: 0.82rem; font-weight: 600; cursor: pointer;
  }}
  .assign-form button:hover {{ background: var(--accent-hover); }}
  .rename-input {{
    background: var(--bg); color: var(--text); border: 1px solid var(--line);
    border-radius: 0.35rem; padding: 0.3rem 0.5rem; font-size: 0.85rem; width: 8rem;
  }}
  .hint {{ color: var(--text-muted); font-size: 0.78rem; margin: 0.6rem 0 0; }}

  .filter-form {{
    display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-bottom: 0.85rem;
  }}
  .filter-form select {{
    background: var(--surface); color: var(--text); border: 1px solid var(--line);
    border-radius: 0.35rem; padding: 0.3rem 0.5rem; font-size: 0.85rem;
  }}
  .filter-form button {{
    background: var(--surface); color: var(--text); border: 1px solid var(--line);
    border-radius: 0.35rem; padding: 0.3rem 0.7rem; font-size: 0.82rem; font-weight: 600; cursor: pointer;
  }}
  .filter-form button:hover {{ border-color: color-mix(in srgb, var(--accent) 50%, transparent); }}

  code {{ font-family: var(--mono); background: var(--bg); padding: 0.1rem 0.3rem; border-radius: 0.25rem; }}
</style></head>
<body>
  <div class="kicker">Home Assistant Add-on</div>
  <h1>Heyra</h1>
  <p class="lede">Acoustic event detection, by AxeForging.</p>

  <a class="primary-action" href="{flash_url}" target="_blank" rel="noopener">
    <strong>Flash a new unit &rarr;</strong>
    <span>Opens the WebSerial flashing page &middot; next available unit ID: {next_unit_id}</span>
  </a>

  <section>
    <h2 class="kicker-sm">Your units</h2>
    <div class="panel">{units_html}</div>
    <p class="hint">Renaming restarts the Add-on (a few seconds of downtime).</p>
  </section>

  <section>
    <h2 class="kicker-sm">Recent events</h2>
    {events_html}
    <p class="hint">Last 200 events, in memory -- for permanent history, see Home
      Assistant's own Logbook for each entity. "Raise alarm" re-publishes the event now,
      through the same pipeline a live detection uses.</p>
  </section>

  <section>
    <h2 class="kicker-sm">Devices found on your network</h2>
    <div class="panel">{discovered_html}</div>
  </section>
</body></html>"""


app = Starlette(
    routes=[
        Route("/", index),
        Route("/assign", assign, methods=["POST"]),
        Route("/reraise", reraise, methods=["POST"]),
        Route("/rename", rename, methods=["POST"]),
    ],
    lifespan=lifespan,
)
