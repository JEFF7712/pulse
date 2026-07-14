"""Load, merge, and emit pulse.toml — all read/write and serialization helpers live here."""

from __future__ import annotations

from pathlib import Path

from pulse.app.config import PulseConfig

from .constants import (
    _CONFIGURE_ENV_KEY_ORDER,
    _CONNECTOR_DEFS,
    _ENV_KEY_TO_CONFIG_FIELD,
    _PULSE_ROOT_FIELD_NAMES,
)


def _env_key_to_pulse_field(ek: str) -> str | None:
    if ek in _ENV_KEY_TO_CONFIG_FIELD:
        return _ENV_KEY_TO_CONFIG_FIELD[ek]
    if ek.startswith("PULSE_"):
        cand = ek[6:].lower()
        if cand in _PULSE_ROOT_FIELD_NAMES:
            return cand
    return None


def _ordered_pulse_root_field_names() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ek in _CONFIGURE_ENV_KEY_ORDER:
        fname = _env_key_to_pulse_field(ek)
        if fname and fname not in seen:
            seen.add(fname)
            out.append(fname)
    for fname in sorted(_PULSE_ROOT_FIELD_NAMES):
        if fname not in seen:
            out.append(fname)
    return out


def _pulse_config_to_working_env(cfg: PulseConfig) -> dict[str, str]:
    out: dict[str, str] = {}
    for fname in _PULSE_ROOT_FIELD_NAMES:
        val = getattr(cfg, fname)
        env_k = f"PULSE_{fname.upper()}"
        if val is None:
            out[env_k] = ""
        elif isinstance(val, bool):
            out[env_k] = "true" if val else "false"
        else:
            out[env_k] = str(val)
    if cfg.anthropic_api_key:
        ak = cfg.anthropic_api_key
        out["ANTHROPIC_API_KEY"] = ak
        out["PULSE_ANTHROPIC_API_KEY"] = ak
    if cfg.openai_api_key:
        out["OPENAI_API_KEY"] = cfg.openai_api_key
    if cfg.gemini_api_key:
        out["GEMINI_API_KEY"] = cfg.gemini_api_key
    return out


def _load_full_pulse_toml(toml_path: Path) -> dict:
    """Parse pulse.toml into a nested dict (empty if missing)."""
    import tomllib

    if not toml_path.exists():
        return {}
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def _load_connectors_state(toml_path: Path) -> dict[str, dict]:
    raw_block: dict = {}
    data = _load_full_pulse_toml(toml_path)
    cc = data.get("connectors")
    if isinstance(cc, dict):
        raw_block = cc
    state: dict[str, dict] = {}
    for name, _, _ in _CONNECTOR_DEFS:
        v = raw_block.get(name)
        state[name] = dict(v) if isinstance(v, dict) else {}
    return state


def _toml_inline_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        esc = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{esc}"'
    raise TypeError(f"Unsupported TOML value type: {type(v)!r}")


def _coerce_pulse_root_string(fname: str, raw: str) -> str | int | bool:
    raw = raw.strip()
    if fname == "smtp_port":
        return int(raw)
    if fname in (
        "smtp_use_tls",
        "smtp_use_ssl",
        "notify_on_job_failure",
    ):
        return raw.lower() in ("1", "true", "yes", "on")
    return raw


def _merge_working_env_into_full_root(full: dict, working_env: dict[str, str]) -> None:
    for ek, fname in _ENV_KEY_TO_CONFIG_FIELD.items():
        if ek not in working_env:
            continue
        v = working_env[ek].strip()
        if v:
            full[fname] = v
        else:
            full.pop(fname, None)
    for key, val in working_env.items():
        if not key.startswith("PULSE_"):
            continue
        fname = key[6:].lower()
        if fname not in _PULSE_ROOT_FIELD_NAMES:
            continue
        v = val.strip()
        if not v:
            full.pop(fname, None)
        else:
            full[fname] = _coerce_pulse_root_string(fname, v)


def _pulse_scalar_empty_for_emit(v: object) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def _emit_pulse_root_scalar_lines(full: dict) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for fname in _ordered_pulse_root_field_names():
        if fname not in full:
            continue
        v = full[fname]
        if _pulse_scalar_empty_for_emit(v):
            continue
        lines.append(f"{fname} = {_toml_inline_value(v)}")
        seen.add(fname)
    for fname in sorted(
        k for k in full if k in _PULSE_ROOT_FIELD_NAMES and k not in seen
    ):
        v = full[fname]
        if _pulse_scalar_empty_for_emit(v):
            continue
        lines.append(f"{fname} = {_toml_inline_value(v)}")
    return lines


def _connector_emit_lines(name: str, sec: dict, default_interval: str) -> list[str]:
    lines: list[str] = []
    enabled = _connector_section_enabled(sec)
    interval = sec.get("poll_interval") or default_interval
    if not isinstance(interval, str):
        interval = str(interval)
    lines.append(f"[connectors.{name}]")
    lines.append(f"enabled = {'true' if enabled else 'false'}")
    lines.append(f'poll_interval = "{interval}"')
    if name == "spotify":
        supp = sec.get("supplementary_interval", "6h")
        if not isinstance(supp, str):
            supp = str(supp)
        lines.append(f'supplementary_interval = "{supp}"')
    if name == "browser":
        bt = sec.get("browser", "chrome")
        if not isinstance(bt, str):
            bt = str(bt)
        lines.append(f'browser = "{bt}"')
        dbp = sec.get("db_path")
        if enabled and isinstance(dbp, str) and dbp.strip():
            safe = dbp.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'db_path = "{safe}"')
    if name == "plaid":
        omit = bool(
            sec.get("omit_amounts_in_summary")
            or sec.get("omit_amounts_in_digest", False)
        )
        lines.append(f"omit_amounts_in_summary = {'true' if omit else 'false'}")
    lines.append("")
    return lines


def _emit_generic_connectors_table(name: str, sec: dict) -> list[str]:
    """Emit [connectors.X] for keys not in _CONNECTOR_DEFS."""
    lines = [f"[connectors.{name}]"]
    for k, v in sorted(sec.items()):
        if isinstance(v, dict):
            continue
        if isinstance(v, list):
            parts = []
            for x in v:
                if isinstance(x, str):
                    sx = x.replace("\\", "\\\\").replace('"', '\\"')
                    parts.append(f'"{sx}"')
                else:
                    parts.append(_toml_inline_value(x))
            lines.append(f"{k} = [" + ", ".join(parts) + "]")
        else:
            lines.append(f"{k} = {_toml_inline_value(v)}")
    lines.append("")
    return lines


def _emit_llm_sections(llm: dict) -> list[str]:
    lines: list[str] = []
    scalars: dict[str, object] = {}
    nested: dict[str, dict] = {}
    for k, v in llm.items():
        if isinstance(v, dict):
            nested[k] = v
        else:
            scalars[k] = v
    if scalars:
        lines.append("[llm]")
        for k in sorted(scalars):
            lines.append(f"{k} = {_toml_inline_value(scalars[k])}")
        lines.append("")
    for sub in ("summarization", "discovery"):
        if sub not in nested:
            continue
        blk = nested[sub]
        if not isinstance(blk, dict) or not blk:
            continue
        lines.append(f"[llm.{sub}]")
        for k in sorted(blk):
            lines.append(f"{k} = {_toml_inline_value(blk[k])}")
        lines.append("")
    for sub, blk in sorted(nested.items()):
        if sub in ("summarization", "discovery"):
            continue
        if not isinstance(blk, dict) or not blk:
            continue
        lines.append(f"[llm.{sub}]")
        for k in sorted(blk):
            lines.append(f"{k} = {_toml_inline_value(blk[k])}")
        lines.append("")
    return lines


def _serialize_pulse_toml_document(full: dict) -> str:
    """Emit pulse.toml: app scalars, connectors, ``[llm]``, then other top-level tables."""
    lines = [
        "# Pulse configuration (single file: paths, secrets, connectors, LLM roles).",
        "# ``PULSE_*`` and vendor API env vars override values from this file when set.",
        "",
    ]
    root_lines = _emit_pulse_root_scalar_lines(full)
    if root_lines:
        lines.append("# --- App (paths, integrations, notifications, API keys) ---")
        lines.extend(root_lines)
        lines.append("")
    connectors = full.get("connectors")
    if not isinstance(connectors, dict):
        connectors = {}
    known = {n for n, _, _ in _CONNECTOR_DEFS}
    for name, default_interval, _label in _CONNECTOR_DEFS:
        sec = connectors.get(name)
        if not isinstance(sec, dict):
            sec = {}
        lines.extend(_connector_emit_lines(name, sec, default_interval))
    for name in sorted(k for k in connectors if k not in known):
        sec = connectors.get(name)
        if isinstance(sec, dict) and sec:
            lines.extend(_emit_generic_connectors_table(name, sec))
    llm = full.get("llm")
    if isinstance(llm, dict) and llm:
        lines.append("# --- LLM (source summarization, discovery) ---")
        lines.append("")
        lines.extend(_emit_llm_sections(llm))
    skip_top = frozenset(("connectors", "llm")) | _PULSE_ROOT_FIELD_NAMES
    for top_key in sorted(k for k in full if k not in skip_top):
        # Forward-compat: extra top-level sections as [key] with flat scalars only.
        block = full[top_key]
        if not isinstance(block, dict):
            continue
        if not block or any(isinstance(v, dict) for v in block.values()):
            continue
        lines.append(f"[{top_key}]")
        for k in sorted(block):
            lines.append(f"{k} = {_toml_inline_value(block[k])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _save_pulse_settings(toml_path: Path, working_env: dict[str, str]) -> None:
    if not (working_env.get("PULSE_SMTP_PORT") or "").strip():
        working_env["PULSE_SMTP_PORT"] = "587"
    full = _load_full_pulse_toml(toml_path)
    _merge_working_env_into_full_root(full, working_env)
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    toml_path.write_text(_serialize_pulse_toml_document(full))


def _write_connectors_state(state: dict[str, dict], toml_path: Path) -> None:
    full = _load_full_pulse_toml(toml_path)
    old_c = full.get("connectors")
    if not isinstance(old_c, dict):
        old_c = {}
    merged = dict(old_c)
    for name, _, _ in _CONNECTOR_DEFS:
        merged[name] = state.get(name) or {}
    full["connectors"] = merged
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    toml_path.write_text(_serialize_pulse_toml_document(full))


def _connector_section_enabled(section: dict) -> bool:
    """True only when this connector block is turned on in pulse.toml.

    Avoid ``bool("false")`` which is True in Python — some hand-edited files use strings.
    """
    if not section:
        return False
    raw = section.get("enabled")
    if raw is True:
        return True
    if raw is False or raw is None:
        return False
    if isinstance(raw, str):
        t = raw.strip().lower()
        return t in ("true", "1", "yes", "on")
    if isinstance(raw, (int, float)):
        return raw != 0
    return False
