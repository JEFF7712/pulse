from pathlib import Path


def test_flake_exposes_package_and_app_outputs() -> None:
    flake = Path("flake.nix").read_text(encoding="utf-8")

    assert "packages.default" in flake
    assert "apps.pulse" in flake or "apps.default" in flake
    assert '"/bin/pulse"' in flake
