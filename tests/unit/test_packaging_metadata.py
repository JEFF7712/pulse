import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_project_metadata_matches_release_install_story() -> None:
    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        project = tomllib.load(fh)["project"]

    assert project["name"] == "pulse-agent"
    assert project["readme"] == "README.md"
    assert project["scripts"]["pulse"] == "pulse.app.cli:main"
    assert project["scripts"]["pulse-mcp"] == "pulse.mcp.server:main"
