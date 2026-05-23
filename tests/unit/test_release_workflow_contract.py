from pathlib import Path


def test_release_workflow_publishes_package_and_docker_image() -> None:
    workflow = Path(".github/workflows/release-publish.yml").read_text(encoding="utf-8")

    assert "tags:" in workflow
    assert "v*" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "docker/build-push-action@v7" in workflow
    assert "scripts/smoke_installed_package.py dist" in workflow
