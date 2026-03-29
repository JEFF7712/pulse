import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, check=True, env=env)


def main(dist_dir: str) -> None:
    wheel = sorted(Path(dist_dir).glob("pulse_agent-*.whl"))[-1]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        venv = root / "venv"
        config_dir = root / "config"
        data_dir = root / "data"
        run([sys.executable, "-m", "venv", str(venv)])
        run([str(venv / "bin" / "pip"), "install", str(wheel)])
        config_dir.mkdir()
        data_dir.mkdir()
        (config_dir / "pulse.toml").write_text("")
        env = {
            **os.environ,
            "PULSE_CONFIG_DIR": str(config_dir),
            "XDG_DATA_HOME": str(root / "xdg-data"),
        }
        run([str(venv / "bin" / "pulse"), "--help"], env=env)
        # pulse-mcp starts the MCP server immediately (no --help flag),
        # so verify it's importable instead of running it.
        run(
            [
                str(venv / "bin" / "python"),
                "-c",
                "from pulse.mcp.server import mcp; print('pulse-mcp entrypoint OK')",
            ],
            env=env,
        )
        run(
            [
                str(venv / "bin" / "python"),
                "-c",
                "from pulse.app.config_loader import load_config; cfg = load_config(); print(cfg.database_path); print(cfg.vault_path)",
            ],
            env=env,
        )


if __name__ == "__main__":
    main(sys.argv[1])
