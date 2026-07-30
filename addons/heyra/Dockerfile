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

# Flashing (esphome + its own Python 3.12 venv, firmware/ source) moved to the public
# WebSerial page -- one shared firmware image, no per-unit compile, nothing left to run
# here. This was the single largest layer in the image; dropping it is the real
# weight-reduction the owner asked for.
COPY listener ./listener
COPY app ./app
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
