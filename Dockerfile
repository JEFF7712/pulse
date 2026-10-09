FROM registry.rupan.dev/upstream/ghcr.io/astral-sh/uv:0.12.11@sha256:79c6f4776b851471cc73b7d21d0cc834bb94383c292e83640d27eff512864df7 AS uv

FROM registry.rupan.dev/upstream/docker.io/library/python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS builder
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml README.md LICENSE uv.lock ./
COPY src ./src
RUN uv build --wheel -o dist

FROM registry.rupan.dev/upstream/docker.io/library/python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

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
