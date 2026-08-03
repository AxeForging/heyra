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
from contextlib import asynccontextmanager

import requests
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from app.discovery import discovery


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
    discovered_html = await render_discovered_html(dict(discovery.devices), sorted(int(u) for u in units))
    return HTMLResponse(STATUS_HTML.format(
        units_html=render_units_html(units),
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


STATUS_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Heyra</title>
<style>
  :root {{
    --bg: #05070a; --surface: #0a0f1a; --line: #1a2233;
    --text: #ffffff; --text-muted: #94a3b8;
    --accent: #ff3b3b; --accent-hover: #e62e2e;
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
    display: block; text-decoration: none; color: inherit;
    background: var(--accent); border-radius: var(--radius);
    padding: 1.1rem 1.35rem;
    box-shadow: 0 16px 32px -18px rgba(255, 59, 59, 0.45);
    transition: background 0.15s ease, transform 0.1s ease;
  }}
  .primary-action:hover {{ background: var(--accent-hover); }}
  .primary-action:active {{ transform: scale(0.99); }}
  .primary-action strong {{ display: block; font-size: 1.05rem; margin-bottom: 0.2rem; }}
  .primary-action span {{ color: rgba(255, 255, 255, 0.85); font-size: 0.85rem; }}

  section {{ margin-top: 2.5rem; }}
  .kicker-sm {{
    font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.85rem;
  }}
  .panel {{
    background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
    box-shadow: 0 24px 48px -32px rgba(0, 0, 0, 0.6);
    overflow: hidden;
  }}
  .empty-note {{ padding: 1.1rem 1.25rem; color: var(--text-muted); font-size: 0.9rem; }}

  .row {{ display: flex; align-items: center; gap: 0.85rem; padding: 0.9rem 1.25rem; }}
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
    background: var(--accent); color: #ffffff; border: none; border-radius: 0.35rem;
    padding: 0.35rem 0.7rem; font-size: 0.82rem; font-weight: 600; cursor: pointer;
  }}
  .assign-form button:hover {{ background: var(--accent-hover); }}

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
    <div class="kicker-sm">Your units</div>
    <div class="panel">{units_html}</div>
  </section>

  <section>
    <div class="kicker-sm">Devices found on your network</div>
    <div class="panel">{discovered_html}</div>
  </section>
</body></html>"""


app = Starlette(
    routes=[
        Route("/", index),
        Route("/assign", assign, methods=["POST"]),
    ],
    lifespan=lifespan,
)
