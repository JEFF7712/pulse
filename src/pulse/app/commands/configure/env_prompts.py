"""Interactive ``input()`` helpers for keep/change env-value prompts."""

from __future__ import annotations

def _mask(value: str) -> str:
    """Show first 8 chars of a secret, mask the rest."""
    if len(value) > 12:
        return f"{value[:8]}..."
    return value


def _prompt_env_field(
    key: str, label: str, current: str, is_secret: bool = False
) -> str:
    """Prompt for an env field. If it already has a value, ask to keep or change."""
    if current:
        display = _mask(current) if is_secret else current
        answer = input(f"  {label}: {display} — keep? [Y/n] ").strip().lower()
        if answer in ("n", "no"):
            new_val = input(f"  {label}: ").strip()
            return new_val if new_val else current
        return current
    else:
        value = input(f"  {label}: ").strip()
        return value



def _configure_section_has_values(env: dict[str, str], fields: list[tuple]) -> bool:
    keys = [f[0] for f in fields]
    return any((env.get(k) or "").strip() for k in keys)


def _offer_bulk_keep_section(
    env: dict[str, str],
    fields: list[tuple],
    section_label: str,
) -> bool:
    """Return True if user wants to keep all existing values for keys in this section."""
    if not _configure_section_has_values(env, fields):
        return False
    ans = input(f"  Keep all existing {section_label}? [Y/n] ").strip().lower()
    return ans not in ("n", "no")


def _prompt_env_field_list(
    fields: list[tuple[str, str, bool]],
    working_env: dict[str, str],
    *,
    offer_bulk_keep: bool,
    section_label: str,
) -> None:
    if offer_bulk_keep and _offer_bulk_keep_section(working_env, fields, section_label):
        return
    for key, label, is_secret in fields:
        current = working_env.get(key, "")
        working_env[key] = _prompt_env_field(key, label, current, is_secret)

