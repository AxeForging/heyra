"""Add-on entrypoint: runs the listener service and the ingress web app
(status + flashing wizard) concurrently in one process, one container.

listener.main.main() already owns its own healthz server internally
(unchanged by this merge) -- this just adds the ingress uvicorn server
alongside it via asyncio.gather, rather than needing a process supervisor
(s6-overlay, etc.) to run two separate processes in one container.
"""
from __future__ import annotations

import asyncio
import os

import uvicorn

from app.main import app as ingress_app
from listener.main import main as listener_main


async def main() -> None:
    ingress_port = int(os.environ.get("INGRESS_PORT", 8099))
    server = uvicorn.Server(uvicorn.Config(ingress_app, host="0.0.0.0", port=ingress_port, log_level="info"))
    await asyncio.gather(listener_main(), server.serve())


if __name__ == "__main__":
    asyncio.run(main())
