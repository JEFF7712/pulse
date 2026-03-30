#!/usr/bin/env bash
# Pulse installer: ensures Python 3.12+, pipx, and pulse-agent from PyPI.
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
    echo "  bash install.sh [--no-onboard]"
    exit 0
    ;;
  esac
done

info() {
  printf '%s\n' "$*"
}

warn() {
  printf '%s\n' "$*" >&2
}

die() {
  warn "$*"
  exit 1
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

PY="$(pick_python)" || die "Pulse needs Python 3.12 or newer. Install from https://www.python.org/downloads/ or your OS package manager, then re-run this script."

info "Using $($PY --version 2>&1)"

export PATH="${HOME}/.local/bin:${PATH}"

have_pipx() {
  command -v pipx >/dev/null 2>&1 && pipx --version >/dev/null 2>&1
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

bootstrap_pipx

if "$PY" -m pipx install pulse-agent; then
  info "Installed pulse-agent with pipx."
else
  die "pipx install pulse-agent failed."
fi

if ! command -v pulse >/dev/null 2>&1; then
  warn "pulse is not on PATH yet. Try: export PATH=\"\$HOME/.local/bin:\$PATH\""
  warn "Or log out and back in after: $PY -m pipx ensurepath"
fi

if [[ "$RUN_ONBOARD" -eq 1 && -t 0 && -t 1 ]]; then
  info ""
  info "Starting interactive setup (pulse onboard)…"
  exec pulse onboard
fi

info ""
info "Next: run  pulse onboard  for interactive setup, then  pulse run  to start the server."
