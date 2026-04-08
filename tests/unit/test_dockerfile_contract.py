from pathlib import Path


def test_runtime_dockerfile_installs_built_wheel() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "COPY dist/ /tmp/dist/" in dockerfile
    assert "pulse_agent-*.whl" in dockerfile
    assert "pip install --no-cache-dir" in dockerfile
    assert "PULSE_CONFIG_DIR=/config" in dockerfile
    assert 'CMD ["pulse", "run"' in dockerfile
