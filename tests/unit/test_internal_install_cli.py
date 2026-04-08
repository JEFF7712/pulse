"""Tests for ``pulse internal-install`` (used by scripts/install.sh)."""

from types import SimpleNamespace

from pulse.app.cli import _internal_install


def test_internal_install_ready_prints_success(capsys):
    _internal_install(SimpleNamespace(phase="ready"))
    out = capsys.readouterr().out
    assert "pulse-agent" in out
    assert "onboard" in out.lower()


def test_internal_install_noninteractive_prints_onboard_hint(capsys):
    _internal_install(SimpleNamespace(phase="noninteractive"))
    out = capsys.readouterr().out.lower()
    assert "onboard" in out
    assert "pulse run" in out
