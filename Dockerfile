# syntax=docker/dockerfile:1.7
FROM python:3.13-slim

ARG PULSE_WHEEL
ENV PULSE_CONFIG_DIR=/config \
    PULSE_DATABASE_PATH=/data/pulse.db \
    PULSE_VAULT_PATH=/data/Pulse-Vault

COPY ${PULSE_WHEEL} /tmp/pulse.whl
RUN pip install --no-cache-dir /tmp/pulse.whl && rm /tmp/pulse.whl

RUN mkdir -p /config /data
VOLUME ["/config", "/data"]
EXPOSE 8000
CMD ["pulse", "run", "--host", "0.0.0.0", "--port", "8000"]
