"""Ingress web UI: shows configured units and their live status.

Flashing moved to the public WebSerial page (axeforging.github.io/heyra/flash.html) --
one shared firmware image, no per-unit compile, so there's no reason for it to run here
anymore. This app is now just a thin status view over listener.healthz's snapshot.
"""
from __future__ import annotations

import html

import requests
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse
from starlette.routing import Route

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


async def index(request):
    snapshot = await run_in_threadpool(fetch_unit_snapshot)
    units = snapshot.get("units", {})
    return HTMLResponse(STATUS_HTML.format(
        units_html=render_units_html(units),
        next_unit_id=next_unit_id(units),
        flash_url=FLASH_URL,
    ))


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
</style></head>
<body>
<h1>Heyra</h1>
<p>Acoustic event detection for Home Assistant, by AxeForging.</p>
<a class="card" href="{flash_url}" target="_blank" rel="noopener"><strong>Flash a unit</strong><span>Opens the WebSerial flashing page (a different site) -- next available unit ID: {next_unit_id}</span></a>
{units_html}
</body></html>"""


app = Starlette(routes=[
    Route("/", index),
])
