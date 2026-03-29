from pathlib import Path


def test_runtime_dockerfile_installs_built_wheel() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "ARG PULSE_WHEEL" in dockerfile
    assert "COPY ${PULSE_WHEEL} /tmp/pulse.whl" in dockerfile
    assert "pip install --no-cache-dir /tmp/pulse.whl" in dockerfile
    assert "PULSE_CONFIG_DIR=/config" in dockerfile
    assert 'CMD ["pulse", "run"' in dockerfile
