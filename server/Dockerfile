FROM python:3.11-slim-bookworm
WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# openWakeWord's SHARED framework assets (melspectrogram/embedding/silero_vad) --
# baked into the image here, not volume-mounted, since they're internal
# dependencies of the library itself, not something a user swaps. The actual
# wakeword classifier model (and yamnet.tflite/class map) live under
# server/models/ on the host and are bind-mounted at runtime instead, so
# swapping in a real trained "help help" model later needs no rebuild.
RUN python -c "import openwakeword.utils; openwakeword.utils.download_models()"

COPY listener ./listener

EXPOSE 6969/udp 8080/tcp
CMD ["python", "-m", "listener.main"]
