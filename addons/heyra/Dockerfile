FROM python:3.11-slim-bookworm
WORKDIR /app

# Not ghcr.io/home-assistant/base -- that's Alpine/musl, which has a real history of
# missing wheels for compiled scientific-Python packages (numpy/tflite-runtime hit
# exactly this ABI trap once already, see CLAUDE.md). HA doesn't require its own base
# image for an Add-on, only recommends it -- a plain Debian-slim Python image is a
# legitimate, and here strictly safer, choice.

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# openWakeWord's SHARED framework assets (melspectrogram/embedding/silero_vad) --
# internal dependencies of the library itself, always baked in here.
RUN python -c "import openwakeword.utils; openwakeword.utils.download_models()"

# esphome needs Python >=3.12; the listener's proven numpy==1.26.4/tflite-runtime==2.14.0
# stack was validated on 3.11 (don't relitigate that ABI landmine). esphome only ever runs
# as a subprocess CLI (compile/upload), never imported as a library, so it doesn't need to
# share an interpreter -- give it its own venv instead of forking the base image. Debian
# bookworm's default apt repos don't carry python3.12, so use uv (already proven in this
# repo, see firmware/ esphome validation) to fetch a standalone Python 3.12 build.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv venv --python 3.12 /opt/esphome-venv \
    && uv pip install --python /opt/esphome-venv/bin/python esphome==2026.7.3

COPY listener ./listener
COPY app ./app
COPY firmware ./firmware
COPY render_config.py run.py ./

# Baked into the image (not volume-mounted): a Supervisor-managed Add-on can only
# mount fixed targets (/share, /config, ...), not an arbitrary host path, so the
# classifier/wake-word models must ship inside the image to work standalone. The
# docker-compose (non-HA) path still bind-mounts over this for fast local swapping
# without a rebuild -- see server/docker-compose.yml.
COPY models ./models

COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
