#!/bin/sh
set -e

python3 /app/render_config.py
exec python3 -m listener.main
