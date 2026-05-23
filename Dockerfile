# syntax=docker/dockerfile:1.24
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml README.md LICENSE uv.lock ./
COPY src ./src
RUN uv build --wheel -o dist

FROM python:3.13-slim

ENV PULSE_CONFIG_DIR=/config \
    PULSE_DATABASE_PATH=/data/pulse.db \
    PULSE_VAULT_PATH=/data/Pulse-Vault

COPY --from=builder /app/dist/ /tmp/dist/
RUN set -eux; \
    wheel="$(ls /tmp/dist/pulse_agent-*.whl | sort -V | tail -n1)"; \
    pip install --no-cache-dir "$wheel"; \
    rm -rf /tmp/dist

RUN mkdir -p /config /data
VOLUME ["/config", "/data"]
EXPOSE 8000
CMD ["pulse", "run", "--host", "0.0.0.0", "--port", "8000"]
