FROM python:3.12-slim-bookworm
WORKDIR /app

# esphome pulls in its own PlatformIO/ESP-IDF toolchain on first compile --
# a genuinely heavy dependency, which is why this is a separate Add-on from
# heyra-listener (ML inference libs) rather than bundled into one image.
# starlette/uvicorn pinned below esphome's own platformio dependency's caps
# (starlette<0.53, uvicorn<0.41) -- not our choice, esphome's transitive constraint.
RUN pip install --no-cache-dir esphome==2026.7.3 starlette==0.52.1 uvicorn==0.40.0

COPY app ./app
COPY firmware ./firmware
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
