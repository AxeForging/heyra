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
import os
import secrets
import shutil
import tempfile
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

FIRMWARE_DIR = Path(os.environ.get("HEYRA_FIRMWARE_DIR", "/app/firmware"))
BOARDS_DIR = FIRMWARE_DIR / "boards"

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


async def index(request):
    boards = list_boards()
    ports = list_serial_ports()
    board_options = "".join(f'<option value="{b}">{b}</option>' for b in boards)
    port_options = "".join(f'<option value="{p}">{p}</option>' for p in ports) or '<option value="">No serial device detected -- plug one in and reload</option>'
    return HTMLResponse(INDEX_HTML.format(board_options=board_options, port_options=port_options))


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
                ("compile", ["esphome", "compile", str(unit_yaml)]),
                ("upload", ["esphome", "upload", str(unit_yaml), "--device", port]),
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


INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Heyra Flasher</title>
<style>
  :root {{ --accent: #ff4e4e; }}
  body {{ font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ border-left: 4px solid var(--accent); padding-left: 0.6rem; }}
  label {{ display: block; margin-top: 0.8rem; font-weight: 600; }}
  input, select {{ width: 100%; padding: 0.4rem; box-sizing: border-box; }}
  button {{ margin-top: 1.2rem; padding: 0.6rem 1.2rem; background: var(--accent); color: white; border: none; border-radius: 4px; cursor: pointer; }}
  pre {{ background: #111; color: #eee; padding: 1rem; margin-top: 1rem; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }}
</style></head>
<body>
<h1>Heyra Flasher</h1>
<p>Plug a unit in over USB, fill this in, hit Flash.</p>
<form id="f">
  <label>Board</label><select name="board">{board_options}</select>
  <label>Serial port</label><select name="port">{port_options}</select>
  <label>Room</label><input name="room" placeholder="kitchen" required>
  <label>Device name</label><input name="device_name" placeholder="atom-echo-02" required>
  <label>Friendly name</label><input name="friendly_name" placeholder="Heyra Kitchen">
  <label>Unit ID</label><input name="unit_id" placeholder="2" required>
  <label>Static IP</label><input name="static_ip" placeholder="192.168.1.102" required>
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
  const resp = await fetch('/api/flash', {{ method: 'POST', body: new FormData(e.target) }});
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
    Route("/api/boards", api_boards),
    Route("/api/ports", api_ports),
    Route("/api/flash", api_flash, methods=["POST"]),
])
