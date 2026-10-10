# Sovereign build: digest-pinned local base, hermetic retained supply.
# Local builds need wheelhouse/ populated first:
#   scripts/fetch-supply.sh
# (wheelhouse/ is gitignored; its contents are retained in Forgejo
# generic packages and pinned in the homelab catalog. Woodpecker
# assembles releases from the same retained supply instead of
# executing this file, and validates that both paths agree.)
FROM registry.rupan.dev/upstream/docker.io/library/python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PULSE_CONFIG_DIR=/config \
    PULSE_DATABASE_PATH=/data/pulse.db \
    PULSE_VAULT_PATH=/data/Pulse-Vault

WORKDIR /app

COPY requirements-prod.txt ./requirements-prod.txt
COPY wheelhouse /wheelhouse

RUN pip install --no-cache-dir --no-index --find-links=/wheelhouse -r ./requirements-prod.txt

COPY src/ src/

RUN printf '#!/usr/local/bin/python\nimport sys\nsys.path.insert(0, "/app/src")\nfrom pulse.app.cli import main as _main\nif __name__ == "__main__":\n    _main()\n' > /usr/local/bin/pulse \
    && printf '#!/usr/local/bin/python\nimport sys\nsys.path.insert(0, "/app/src")\nfrom pulse.mcp.server import main as _main\nif __name__ == "__main__":\n    _main()\n' > /usr/local/bin/pulse-mcp \
    && chmod 0755 /usr/local/bin/pulse /usr/local/bin/pulse-mcp \
    && mkdir -p /config /data

VOLUME ["/config", "/data"]
EXPOSE 8000
CMD ["pulse", "run", "--host", "0.0.0.0", "--port", "8000"]
