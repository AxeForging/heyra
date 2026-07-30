#!/bin/sh
set -e

exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${INGRESS_PORT:-8099}"
