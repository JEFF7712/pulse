#!/usr/bin/env bash

set -euo pipefail

image="pulse-landing-page-test"
container="pulse-landing-page-smoke-$$"

cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
}

trap cleanup EXIT

[[ -f index.html ]]
grep -q '^FROM nginx:alpine$' Dockerfile
grep -q '^EXPOSE 8080$' Dockerfile
grep -q '^USER 101:101$' Dockerfile

docker build -t "$image" . >/dev/null
docker run -d --rm --name "$container" -p 127.0.0.1::8080 "$image" >/dev/null

port_line="$(docker port "$container" 8080/tcp)"
port="${port_line##*:}"

for _ in {1..20}; do
  if html="$(curl -fsS "http://127.0.0.1:$port/")"; then
    break
  fi
  sleep 1
done

[[ -n "${html:-}" ]]
grep -q '<title>Pulse</title>' <<<"$html"
grep -q 'Personal Intelligence Agent' <<<"$html"
grep -q '<form' <<<"$html"
grep -q 'class="signup-form"' <<<"$html"
grep -q 'id="signupForm"' <<<"$html"
grep -q 'method="POST"' <<<"$html"
grep -q 'action="https://formspree.io/f/mreywkbd"' <<<"$html"
grep -q 'type="email"' <<<"$html"
grep -q 'name="email"' <<<"$html"
grep -q 'required' <<<"$html"
node tests/signup-runtime-behavior.js
grep -q 'Notify Me' <<<"$html"
