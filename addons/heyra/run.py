"""Add-on entrypoint: runs the listener service and the ingress web app
(status + flashing wizard) concurrently in one process, one container.

listener.main.main() already owns its own healthz server internally
(unchanged by this merge) -- this just adds the ingress uvicorn server
alongside it via asyncio.gather, rather than needing a process supervisor
(s6-overlay, etc.) to run two separate processes in one container.
"""
from __future__ import annotations

import asyncio
import logging
import os

import requests
import uvicorn

from app.main import app as ingress_app
from listener.main import main as listener_main

log = logging.getLogger("heyra.run")

DEFAULT_INGRESS_PORT = 8099


def get_ingress_port() -> int:
    """config.yaml sets ingress_port: 0 (required under host_network: true) -- Supervisor
    assigns a real port from its own dynamic range (62000-65500) and expects the add-on to
    fetch it via the Supervisor API. There is no env var carrying it (confirmed against the
    real ESPHome Add-on's own startup code, which does the same GET call via bashio) -- a
    hardcoded fallback here is exactly what caused a live 502: uvicorn bound to
    DEFAULT_INGRESS_PORT while Supervisor's ingress proxy tried to reach the real assigned
    port, which nothing was listening on. Falls back to DEFAULT_INGRESS_PORT only outside a
    real Supervisor environment (local `docker run`/docker-compose, no SUPERVISOR_TOKEN)."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return DEFAULT_INGRESS_PORT
    try:
        resp = requests.get(
            "http://supervisor/addons/self/info",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        resp.raise_for_status()
        port = resp.json()["data"]["ingress_port"]
        if port:
            return int(port)
    except Exception:
        log.warning("could not fetch ingress_port from Supervisor API, falling back to %d", DEFAULT_INGRESS_PORT)
    return DEFAULT_INGRESS_PORT


async def main() -> None:
    ingress_port = get_ingress_port()
    log.info("binding ingress web app to port %d", ingress_port)
    server = uvicorn.Server(uvicorn.Config(ingress_app, host="0.0.0.0", port=ingress_port, log_level="info"))
    await asyncio.gather(listener_main(), server.serve())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
