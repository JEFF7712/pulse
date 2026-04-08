# syntax=docker/dockerfile:1.7
FROM python:3.13-slim

ENV PULSE_CONFIG_DIR=/config \
    PULSE_DATABASE_PATH=/data/pulse.db \
    PULSE_VAULT_PATH=/data/Pulse-Vault

# Copy all build artifacts; install the pulse_agent wheel (avoids COPY glob + build-arg issues in CI).
COPY dist/ /tmp/dist/
RUN set -eux; \
    wheel="$(ls /tmp/dist/pulse_agent-*.whl | sort -V | tail -n1)"; \
    pip install --no-cache-dir "$wheel"; \
    rm -rf /tmp/dist

RUN mkdir -p /config /data
VOLUME ["/config", "/data"]
EXPOSE 8000
CMD ["pulse", "run", "--host", "0.0.0.0", "--port", "8000"]
