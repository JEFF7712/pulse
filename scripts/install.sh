#!/usr/bin/env bash
# Pulse installer: ensures Python 3.12+, pipx, and pulse-agent from PyPI.
# Styling matches the Pulse CLI (accent green, cream labels); Rich output after install.
#
# Usage: curl -fsSL https://pulseagent.dev/install.sh | bash
#        curl -fsSL https://pulseagent.dev/install.sh | bash -s -- --no-onboard

set -euo pipefail

RUN_ONBOARD=1
for arg in "$@"; do
  case "$arg" in
  --no-onboard) RUN_ONBOARD=0 ;;
  --help | -h)
    echo "Pulse install script"
    echo "  curl -fsSL https://pulseagent.dev/install.sh | bash"
    echo "  bash install.sh [--no-onboard]   # skip automatic pulse onboard"
    exit 0
    ;;
  esac
done

# Truecolor + weight, aligned with src/pulse/app/cli_ui.py (SITE_ACCENT, SITE_CREAM, SITE_MUTED_FG).
if [[ -t 1 ]]; then
  ACCENT=$'\033[1;38;2;74;222;128m'
  CREAM=$'\033[38;2;196;191;184m'
  MUTED=$'\033[2;38;2;168;162;158m'
  WARN=$'\033[1;38;2;251;191;36m'
  BOLD=$'\033[1m'
  RESET=$'\033[0m'
  DIM=$'\033[2m'
else
  ACCENT=""
  CREAM=""
  MUTED=""
  WARN=""
  BOLD=""
  RESET=""
  DIM=""
fi

rule() {
  local title="$1"
  local width=52
  local pad=$((width - ${#title} - 2))
  [[ $pad -lt 2 ]] && pad=2
  local i
  printf '%s' "$ACCENT"
  for ((i = 0; i < 3; i++)); do printf '─'; done
  printf '%s' "$RESET"
  printf ' %s%s%s ' "$BOLD$CREAM" "$title" "$RESET"
  printf '%s' "$ACCENT"
  for ((i = 0; i < pad; i++)); do printf '─'; done
  printf '%s\n' "$RESET"
}

banner() {
  local line1="${ACCENT}●${RESET} ${ACCENT}${BOLD}PULSE${RESET} ${CREAM}CLI${RESET}  ${MUTED}install · self-hosted${RESET}"
  local line2="${MUTED}https://pulseagent.dev${RESET}"
  local inner="${line1}"$'\n'"${line2}"
  local border="${ACCENT}"
  printf '%b\n' "${border}╭────────────────────────────────────────────────────╮${RESET}"
  while IFS= read -r line; do
    printf '%b %s %b\n' "${border}│${RESET}" "$line" "${border}│${RESET}"
  done <<< "$inner"
  printf '%b\n' "${border}╰────────────────────────────────────────────────────╯${RESET}"
}

step() {
  printf '%b %s%s%s\n' "${ACCENT}▸${RESET}" "$BOLD" "$1" "$RESET"
}

ok() {
  printf '%b %s\n' "${ACCENT}✓${RESET}" "$1"
}

warn() {
  printf '%b %s\n' "${WARN}⚠${RESET}" "$*" >&2
}

die() {
  printf '%b %s\n' "${ACCENT}✗${RESET} $*" >&2
  exit 1
}

info_muted() {
  printf '%s\n' "${MUTED}$*${RESET}"
}

pick_python() {
  local c
  for c in python3.13 python3.12 python3; do
    if command -v "$c" >/dev/null 2>&1 \
      && "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      printf '%s' "$c"
      return 0
    fi
  done
  return 1
}

require_venv_works() {
  local d out
  d="$(mktemp -d)"
  out="$(mktemp)"
  if "$PY" -m venv "$d" >"$out" 2>&1; then
    rm -rf "$d" "$out"
    return 0
  fi
  local ver hint
  ver="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo X.Y)"
  hint="sudo apt install python${ver}-venv"
  if grep -q 'ensurepip is not available' "$out" 2>/dev/null; then
    rm -rf "$d" "$out"
    die "pipx needs Python's venv module (ensurepip). On Debian/Ubuntu run:
  $hint
  (or  sudo apt install python3-venv  for the default Python)
Then re-run this installer."
  fi
  rm -rf "$d"
  warn "venv check failed:"
  cat "$out" >&2 || true
  rm -f "$out"
  die "Fix the error above, then re-run. On Debian/Ubuntu you may need: $hint"
}

bootstrap_pipx() {
  if have_pipx; then
    return 0
  fi

  if ! "$PY" -m pip --version >/dev/null 2>&1; then
    die "pip is not available for $PY. Install pip (e.g. python3-pip) and re-run."
  fi

  local log
  log="$(mktemp)"
  if "$PY" -m pip install --user pipx 2>"$log"; then
    :
  elif grep -q 'externally-managed-environment' "$log" 2>/dev/null \
    && "$PY" -m pip install --user --break-system-packages pipx; then
    :
  else
    warn "Could not install pipx automatically. Log:"
    cat "$log" >&2 || true
    rm -f "$log"
    die "Install pipx manually (https://pipx.pypa.io/stable/installation/) — e.g. apt: sudo apt install pipx · brew: brew install pipx — then re-run this script."
  fi
  rm -f "$log"

  if "$PY" -m pipx ensurepath >/dev/null 2>&1; then
    :
  else
    warn "Note: run '$PY -m pipx ensurepath' if the pulse command is not found, then open a new terminal."
  fi

  export PATH="${HOME}/.local/bin:${PATH}"
  have_pipx || die "pipx did not install correctly. Try a new shell or add ~/.local/bin to PATH."
}

have_pipx() {
  command -v pipx >/dev/null 2>&1 && pipx --version >/dev/null 2>&1
}

run_pulse_ui() {
  local phase="$1"
  if command -v pulse >/dev/null 2>&1 && pulse internal-install "$phase" 2>/dev/null; then
    return 0
  fi
  case "$phase" in
  ready)
    ok "pulse-agent installed with pipx"
    info_muted "Run: pulse onboard   then: pulse run"
    ;;
  noninteractive)
    warn "Could not open this CLI's styled installer (upgrade pulse-agent, or run manually)."
    info_muted "  pulse onboard"
    info_muted "  pulse run"
    ;;
  esac
}

banner
rule "Install pulse-agent"
printf '\n'

step "Python"
PY="$(pick_python)" || die "Pulse needs Python 3.12 or newer. Install from https://www.python.org/downloads/ or your OS package manager, then re-run this script."
ok "Using $($PY --version 2>&1)"

step "venv (required for pipx)"
require_venv_works
ok "venv module available"

export PATH="${HOME}/.local/bin:${PATH}"

step "pipx"
bootstrap_pipx
ok "pipx ready"

step "Install pulse-agent from PyPI"
set +e
PIP_OUT="$(mktemp)"
if pipx install --quiet pulse-agent >"$PIP_OUT" 2>&1; then
  rm -f "$PIP_OUT"
  set -e
else
  cat "$PIP_OUT" >&2 || true
  rm -f "$PIP_OUT"
  set -e
  die "pipx install pulse-agent failed."
fi

hash -r 2>/dev/null || true
export PATH="${HOME}/.local/bin:${PATH}"

printf '\n'
run_pulse_ui ready
printf '\n'

if ! command -v pulse >/dev/null 2>&1; then
  warn "pulse is not on PATH yet."
  info_muted "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  info_muted "Or log out and back in after: $PY -m pipx ensurepath"
  printf '\n'
fi

if [[ "$RUN_ONBOARD" -eq 1 ]]; then
  if [[ -t 0 && -t 1 ]]; then
    exec pulse onboard
  elif [[ -r /dev/tty && -w /dev/tty && -t 1 ]]; then
    exec pulse onboard < /dev/tty
  else
    run_pulse_ui noninteractive
  fi
else
  step "Onboarding"
  info_muted "Skipped (--no-onboard). When ready: pulse onboard"
  printf '\n'
fi
