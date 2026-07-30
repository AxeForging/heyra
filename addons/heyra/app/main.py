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
        return (
            '<div class="card"><strong>Your units</strong>'
            "<span>No units configured yet, or the listener is still starting up.</span></div>"
        )
    rows = []
    for unit_id in sorted(units, key=int):
        u = units[unit_id]
        status = "online" if u.get("online") else "offline"
        age = u.get("last_packet_age_s")
        age_text = f"{age:.0f}s ago" if age is not None else "never"
        rows.append(
            '<div class="unit-row">'
            f'<span class="dot dot-{status}"></span>'
            f'<strong>{html.escape(str(u.get("room", "?")))}</strong>'
            f'<span class="unit-meta">unit {html.escape(str(unit_id))} &middot; {status} &middot; last packet {age_text}</span>'
            "</div>"
        )
    return '<div class="card"><strong>Your units</strong>' + "".join(rows) + "</div>"


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
        return ""
    hostnames = sorted(devices)
    current_ids = await asyncio.gather(*(run_in_threadpool(fetch_device_unit_id, h) for h in hostnames))
    options = "".join(f'<option value="{uid}">{uid}</option>' for uid in configured_unit_ids)
    rows = []
    for hostname, current_id in zip(hostnames, current_ids):
        current_text = f"currently reports unit {current_id}" if current_id is not None else "not reachable yet"
        rows.append(
            '<div class="unit-row">'
            f'<strong>{html.escape(hostname)}</strong>'
            f'<span class="unit-meta">{current_text}</span>'
            f'<form method="post" action="assign" class="assign-form">'
            f'<input type="hidden" name="hostname" value="{html.escape(hostname)}">'
            f'<select name="unit_id">{options}</select>'
            '<button type="submit">Assign</button>'
            "</form>"
            "</div>"
        )
    return '<div class="card"><strong>Devices found on your network</strong>' + "".join(rows) + "</div>"


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
    return RedirectResponse(url="/", status_code=303)


STATUS_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Heyra</title>
<style>
  :root {{ --bg: #05070a; --surface: #0a0f1a; --line: #1a2233; --text: #ffffff; --text-muted: #94a3b8; --accent: #ff3b3b; --accent-hover: #e62e2e; --online: #22c55e; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Inter", ui-sans-serif, system-ui, sans-serif; background: var(--bg); color: var(--text); max-width: 640px; margin: 3rem auto; padding: 0 1rem; }}
  h1 {{ font-weight: 700; letter-spacing: -0.02em; }}
  p {{ color: var(--text-muted); }}
  a.card, div.card {{ display: block; padding: 1.1rem 1.25rem; margin-top: 1rem; background: var(--surface); border: 1px solid var(--line); border-radius: 0.5rem; text-decoration: none; color: inherit; transition: border-color 0.15s ease; }}
  a.card:hover {{ border-color: var(--accent); }}
  a.card strong, div.card strong {{ display: block; margin-bottom: 0.3rem; }}
  a.card span, div.card span {{ color: var(--text-muted); font-size: 0.9rem; }}
  code {{ font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace; background: var(--bg); padding: 0.1rem 0.3rem; border-radius: 0.25rem; }}
  .unit-row {{ display: flex; align-items: baseline; gap: 0.5rem; padding: 0.5rem 0; border-top: 1px solid var(--line); }}
  .unit-row:first-of-type {{ border-top: none; margin-top: 0.6rem; }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); flex: none; }}
  .dot-online {{ background: var(--online); }}
  .unit-meta {{ color: var(--text-muted); font-size: 0.85rem; }}
  .assign-form {{ display: flex; align-items: center; gap: 0.4rem; margin-left: auto; }}
  .assign-form select {{ background: var(--bg); color: var(--text); border: 1px solid var(--line); border-radius: 0.3rem; padding: 0.2rem 0.4rem; font-size: 0.85rem; }}
  .assign-form button {{ background: var(--accent); color: #ffffff; border: none; border-radius: 0.3rem; padding: 0.25rem 0.6rem; font-size: 0.85rem; font-weight: 600; cursor: pointer; }}
  .assign-form button:hover {{ background: var(--accent-hover); }}
</style></head>
<body>
<h1>Heyra</h1>
<p>Acoustic event detection for Home Assistant, by AxeForging.</p>
<a class="card" href="{flash_url}" target="_blank" rel="noopener"><strong>Flash a unit</strong><span>Opens the WebSerial flashing page (a different site) -- next available unit ID: {next_unit_id}</span></a>
{units_html}
{discovered_html}
</body></html>"""


app = Starlette(
    routes=[
        Route("/", index),
        Route("/assign", assign, methods=["POST"]),
    ],
    lifespan=lifespan,
)
