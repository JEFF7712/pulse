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
grep -q 'Self-Hosted Personal Intelligence Agent' <<<"$html"
grep -q 'Turns your life data into useful observations' <<<"$html"
grep -q 'see what matters and act on it\.' <<<"$html"
grep -q 'Pulse connects the tools you already use' <<<"$html"
grep -q 'useful observations to your vault\.' <<<"$html"
grep -q 'late meetings are pushing dinner' <<<"$html"
grep -q 'sleep shorter' <<<"$html"
grep -q 'two' <<<"$html"
grep -q 'strength workouts are your most focused workweeks' <<<"$html"
grep -q 'Every observation lands as readable notes' <<<"$html"
grep -q 'Obsidian' <<<"$html"
grep -q 'Together they turn scattered signals into one readable picture' <<<"$html"
grep -q 'Self-hosted, readable, and under your control\.' <<<"$html"
[[ "$(grep -o '<h3>' <<<"$html" | wc -l | tr -d ' ')" -eq 3 ]]
grep -q '<h3>Self-Hosted</h3>' <<<"$html"
grep -q 'Pulse runs on your hardware' <<<"$html"
grep -q '<h3>Readable Notes</h3>' <<<"$html"
grep -q 'plain-language notes' <<<"$html"
grep -q '<h3>User Control</h3>' <<<"$html"
grep -q 'inspect, edit, or delete what it keeps' <<<"$html"
! grep -q '<h3>On Your Terms</h3>' <<<"$html"
grep -q '<form' <<<"$html"
grep -q 'class="signup-form"' <<<"$html"
grep -q 'id="signupForm"' <<<"$html"
grep -q 'method="POST"' <<<"$html"
grep -q 'action="https://formspree.io/f/mreywkbd"' <<<"$html"
grep -q 'type="email"' <<<"$html"
grep -q 'name="email"' <<<"$html"
grep -q 'required' <<<"$html"
node tests/signup-runtime-behavior.js
grep -q 'Join the first Pulse early access cohort\.' <<<"$html"
grep -q 'If you care about self-hosting, personal knowledge systems, and quantified-self style tools, Pulse is for you\.' <<<"$html"
grep -q 'Request Early Access' <<<"$html"
! grep -q 'Notify Me' <<<"$html"
! grep -q 'This is being built in the open\.' <<<"$html"
! grep -q 'Leave your email to get notified when Pulse launches\.' <<<"$html"
