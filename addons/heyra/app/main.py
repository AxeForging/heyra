"""Ingress web UI: pick a board + fill in unit details, flash over USB.

Deliberately thin -- generates a unit YAML from firmware/boards/<board>.yaml
+ firmware/common.yaml (the same packages: pattern firmware/units/*.yaml
uses), writes a secrets.yaml from the form fields, then shells out to the
real `esphome` CLI (compile, then upload) and streams its output back to
the browser as it runs. No PlatformIO/ESP-IDF reimplementation -- esphome
already does that well.
"""
from __future__ import annotations

import asyncio
import glob
import html
import os
import secrets
import shutil
import tempfile
from pathlib import Path

import requests
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

FIRMWARE_DIR = Path(os.environ.get("HEYRA_FIRMWARE_DIR", "/app/firmware"))
BOARDS_DIR = FIRMWARE_DIR / "boards"
# esphome lives in its own Python 3.12 venv (see Dockerfile) -- the listener/ingress
# app runs under 3.11, doesn't need to share an interpreter with a CLI subprocess.
ESPHOME_BIN = os.environ.get("HEYRA_ESPHOME_BIN", "/opt/esphome-venv/bin/esphome")
# listener.healthz binds this in the same container/process (see run.py) -- loopback,
# not proxied through Ingress, so this call never leaves the container.
HEALTHZ_URL = "http://127.0.0.1:8080/healthz"

UNIT_TEMPLATE = """substitutions:
  room: {room}
  device_name: {device_name}
  friendly_name: "{friendly_name}"
  unit_id: "{unit_id}"
  static_ip: {static_ip}

packages:
  board: !include {board_path}
  base: !include {common_path}
"""

SECRETS_TEMPLATE = """wifi_ssid: "{wifi_ssid}"
wifi_password: "{wifi_password}"
api_encryption_key: "{api_encryption_key}"
ota_password: "{ota_password}"
"""


def list_boards() -> list[str]:
    return sorted(p.stem for p in BOARDS_DIR.glob("*.yaml"))


def list_serial_ports() -> list[str]:
    return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))


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
    units_html = render_units_html(snapshot.get("units", {}))
    return HTMLResponse(STATUS_HTML.format(units_html=units_html))


async def flash_page(request):
    boards = list_boards()
    ports = list_serial_ports()
    snapshot = await run_in_threadpool(fetch_unit_snapshot)
    board_options = "".join(f'<option value="{b}">{b}</option>' for b in boards)
    port_options = "".join(f'<option value="{p}">{p}</option>' for p in ports) or '<option value="">No serial device detected -- plug one in and reload</option>'
    return HTMLResponse(FLASH_HTML.format(
        board_options=board_options,
        port_options=port_options,
        next_unit_id=next_unit_id(snapshot.get("units", {})),
    ))


async def api_boards(request):
    return JSONResponse(list_boards())


async def api_ports(request):
    return JSONResponse(list_serial_ports())


async def api_flash(request):
    form = await request.form()
    board = form.get("board", "")
    port = form.get("port", "")
    if board not in list_boards():
        return JSONResponse({"error": f"unknown board '{board}'"}, status_code=400)
    if not port:
        return JSONResponse({"error": "no serial port selected"}, status_code=400)

    workdir = Path(tempfile.mkdtemp(prefix="heyra-flash-"))
    unit_yaml = workdir / "unit.yaml"
    secrets_yaml = workdir / "secrets.yaml"
    unit_yaml.write_text(UNIT_TEMPLATE.format(
        room=form.get("room", "unset"),
        device_name=form.get("device_name", "heyra-unit"),
        friendly_name=form.get("friendly_name", "Heyra Unit"),
        unit_id=form.get("unit_id", "1"),
        static_ip=form.get("static_ip", "192.168.1.100"),
        board_path=BOARDS_DIR / f"{board}.yaml",
        common_path=FIRMWARE_DIR / "common.yaml",
    ))
    secrets_yaml.write_text(SECRETS_TEMPLATE.format(
        wifi_ssid=form.get("wifi_ssid", ""),
        wifi_password=form.get("wifi_password", ""),
        api_encryption_key=secrets.token_bytes(32).hex(),
        ota_password=secrets.token_hex(16),
    ))

    async def stream_flash():
        try:
            for step_label, cmd in (
                ("compile", [ESPHOME_BIN, "compile", str(unit_yaml)]),
                ("upload", [ESPHOME_BIN, "upload", str(unit_yaml), "--device", port]),
            ):
                yield f"\n=== {step_label} ===\n".encode()
                proc = await asyncio.create_subprocess_exec(
                    *cmd, cwd=workdir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                )
                async for line in proc.stdout:
                    yield line
                returncode = await proc.wait()
                if returncode != 0:
                    yield f"\n=== {step_label} failed (exit {returncode}) ===\n".encode()
                    return
            yield b"\n=== done -- unit flashed ===\n"
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    return StreamingResponse(stream_flash(), media_type="text/plain")


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
<p>Acoustic event detection + firmware flashing, by AxeForging.</p>
<a class="card" href="flash"><strong>Flash a unit</strong><span>Compile and flash Heyra firmware onto a new ATOM Echo over USB</span></a>
{units_html}
</body></html>"""

FLASH_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Heyra Flasher</title>
<style>
  :root {{ --bg: #05070a; --surface: #0a0f1a; --line: #1a2233; --text: #ffffff; --text-muted: #94a3b8; --accent: #ff3b3b; --accent-hover: #e62e2e; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Inter", ui-sans-serif, system-ui, sans-serif; background: var(--bg); color: var(--text); max-width: 640px; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ font-weight: 700; letter-spacing: -0.02em; }}
  p {{ color: var(--text-muted); }}
  label {{ display: block; margin-top: 0.8rem; font-weight: 600; font-size: 0.9rem; }}
  input, select {{ width: 100%; padding: 0.5rem 0.6rem; margin-top: 0.3rem; background: var(--surface); color: var(--text); border: 1px solid var(--line); border-radius: 0.4rem; }}
  input:focus, select:focus {{ outline: none; border-color: var(--accent); }}
  button {{ margin-top: 1.2rem; padding: 0.6rem 1.2rem; background: var(--accent); color: #ffffff; border: none; border-radius: 0.4rem; font-weight: 600; cursor: pointer; }}
  button:hover {{ background: var(--accent-hover); }}
  pre {{ font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace; background: var(--surface); border: 1px solid var(--line); color: var(--text); padding: 1rem; margin-top: 1rem; white-space: pre-wrap; max-height: 400px; overflow-y: auto; border-radius: 0.4rem; }}
</style></head>
<body>
<h1>Heyra Flasher</h1>
<p>Plug a unit in over USB, fill this in, hit Flash.</p>
<form id="f">
  <label>Board</label><select name="board">{board_options}</select>
  <label>Serial port</label><select name="port">{port_options}</select>
  <label>Room</label><input name="room" placeholder="kitchen" required>
  <label>Device name</label><input name="device_name" placeholder="e.g. atom-echo-03" required>
  <label>Friendly name</label><input name="friendly_name" placeholder="Heyra Kitchen">
  <label>Unit ID</label><input name="unit_id" value="{next_unit_id}" required>
  <label>Static IP</label><input name="static_ip" placeholder="e.g. 192.168.1.10x -- pick one unused" required>
  <label>WiFi SSID</label><input name="wifi_ssid" required>
  <label>WiFi password</label><input name="wifi_password" type="password" required>
  <button type="submit">Flash</button>
</form>
<pre id="log" style="display:none"></pre>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const log = document.getElementById('log');
  log.style.display = 'block';
  log.textContent = '';
  const resp = await fetch('api/flash', {{ method: 'POST', body: new FormData(e.target) }});
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  while (true) {{
    const {{ done, value }} = await reader.read();
    if (done) break;
    log.textContent += decoder.decode(value, {{ stream: true }});
    log.scrollTop = log.scrollHeight;
  }}
}});
</script>
</body></html>"""


app = Starlette(routes=[
    Route("/", index),
    Route("/flash", flash_page),
    Route("/api/boards", api_boards),
    Route("/api/ports", api_ports),
    Route("/api/flash", api_flash, methods=["POST"]),
])
