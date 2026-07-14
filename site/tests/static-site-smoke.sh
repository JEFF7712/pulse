#!/usr/bin/env bash

set -euo pipefail

image="pulse-landing-page-test"
container="pulse-landing-page-smoke-$$"

assert_contains() {
  local body="$1"
  local needle="$2"

  grep -Fq "$needle" <<<"$body"
}

cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
}

trap cleanup EXIT

# CI (e.g. GitHub Actions + Docker) can briefly reset connections while nginx
# binds the port; curl (56) otherwise fails the single-shot requests below.
curl_nginx() {
  curl -fsS \
    --connect-timeout 5 \
    --max-time 60 \
    --retry 12 \
    --retry-delay 1 \
    --retry-all-errors \
    "$@"
}

[[ -f index.html ]]
[[ -f ../scripts/install.sh ]]
[[ -f ../docs/index.md ]]
[[ ! -f docs/index.html ]]
[[ -f docs-app/package.json ]]
[[ -f docs-app/package-lock.json ]]
[[ -f docs-app/.gitignore ]]
[[ -f docs-app/docs/.vitepress/config.mts ]]
[[ -f docs-app/docs/index.md ]]
[[ -f docs-app/docs/.vitepress/theme/custom.css ]]
[[ -f docs-app/docs/.vitepress/theme/index.ts ]]
grep -qx 'node_modules' docs-app/.gitignore
grep -qx 'docs/.vitepress/cache' docs-app/.gitignore
grep -qx 'docs/.vitepress/dist' docs-app/.gitignore
! grep -q '^\.vitepress/' docs-app/.gitignore
grep -q 'base: "/docs/"' docs-app/docs/.vitepress/config.mts
grep -q 'import "./custom.css";' docs-app/docs/.vitepress/theme/index.ts
grep -q '^  --vp-font-family-base: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",$' docs-app/docs/.vitepress/theme/custom.css
grep -q '^  --vp-font-family-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco,$' docs-app/docs/.vitepress/theme/custom.css
grep -q '^\.pulse-docs-home \.vp-doc > div {$' docs-app/docs/.vitepress/theme/custom.css
npm ci --ignore-scripts --no-audit --no-fund --prefix docs-app >/dev/null
grep -q '^FROM node:20-alpine AS docs-builder$' Dockerfile
grep -q '^WORKDIR /app/site/docs-app$' Dockerfile
grep -q '^COPY site/docs-app/package.json site/docs-app/package-lock.json \./$' Dockerfile
grep -q '^RUN npm ci --ignore-scripts --no-audit --no-fund$' Dockerfile
grep -q '^COPY site/docs-app/ \./$' Dockerfile
grep -q '^COPY docs/ /app/docs/$' Dockerfile
grep -q '^RUN npm run docs:build$' Dockerfile
grep -q '^FROM nginx:alpine$' Dockerfile
grep -q '^COPY site/nginx.conf /etc/nginx/nginx.conf$' Dockerfile
grep -q '^COPY site/index.html /usr/share/nginx/html/index.html$' Dockerfile
grep -q '^COPY scripts/install.sh /usr/share/nginx/html/install.sh$' Dockerfile
grep -q '^COPY site/pulse-mark\.svg /usr/share/nginx/html/pulse-mark\.svg$' Dockerfile
[[ -f pulse-mark.svg ]]
grep -q 'src="pulse-mark\.svg"' index.html
grep -q 'href="pulse-mark\.svg"' index.html
grep -q '^COPY --from=docs-builder /app/site/docs-app/docs/\.vitepress/dist/favicon\.ico /usr/share/nginx/html/favicon\.ico$' Dockerfile
grep -q '^COPY --from=docs-builder /app/site/docs-app/docs/\.vitepress/dist/ /usr/share/nginx/html/docs/$' Dockerfile
grep -q '^EXPOSE 8080$' Dockerfile
grep -q '^USER 101:101$' Dockerfile
grep -qx '\.env' ../.dockerignore
grep -qx '\.venv/' ../.dockerignore
grep -qx 'data/' ../.dockerignore
grep -qx 'Pulse-Vault/' ../.dockerignore

docker build -f Dockerfile -t "$image" .. >/dev/null
docker run -d --rm --name "$container" -p 127.0.0.1::8080 "$image" >/dev/null

port_line="$(docker port "$container" 8080/tcp)"
port="${port_line##*:}"

for _ in {1..20}; do
  if html="$(curl_nginx "http://127.0.0.1:$port/")"; then
    break
  fi
  sleep 1
done

for _ in {1..20}; do
  if docs_bridge_html="$(curl_nginx "http://127.0.0.1:$port/docs/")"; then
    break
  fi
  sleep 1
done

docs_html="$docs_bridge_html"
quickstart_html="$(curl_nginx "http://127.0.0.1:$port/docs/self-hosting/quickstart.html")"
install_sh_body="$(curl_nginx "http://127.0.0.1:$port/install.sh")"
configuration_html="$(curl_nginx "http://127.0.0.1:$port/docs/reference/configuration.html")"
runbook_html="$(curl_nginx "http://127.0.0.1:$port/docs/operations/runbook.html")"
connectors_html="$(curl_nginx "http://127.0.0.1:$port/docs/connectors/")"
docs_asset_path="$(grep -Eo '/docs/assets/[^"[:space:]]*' <<<"$docs_html" | head -n 1)"
docs_nav_path="$(grep -Eo '/docs/self-hosting/quickstart\.html[^"[:space:]]*' <<<"$docs_html" | head -n 1)"

[[ -n "$docs_asset_path" ]]
[[ -n "$docs_nav_path" ]]

curl_nginx "http://127.0.0.1:$port$docs_asset_path" >/dev/null
curl_nginx "http://127.0.0.1:$port$docs_nav_path" >/dev/null

[[ -n "${html:-}" ]]
[[ -n "${docs_html:-}" ]]
[[ -n "${docs_bridge_html:-}" ]]
grep -q '<title>Pulse</title>' <<<"$html"
grep -q 'https://pulseagent.dev/docs/' <<<"$html"
grep -q 'Personal intelligence agent' <<<"$html"
grep -q 'Turn your life data into useful observations\.' <<<"$html"
# Phrase is split across lines in index.html; match stable parts.
grep -q 'It explains what' <<<"$html"
grep -q 'is changing in plain English' <<<"$html"
grep -q 'Pulse connects the tools you already use' <<<"$html"
grep -q 'useful observations to your vault\.' <<<"$html"
grep -q 'late meetings are pushing dinner' <<<"$html"
grep -q 'sleep shorter' <<<"$html"
grep -q 'weeks with two strength workouts' <<<"$html"
grep -q 'most focused' <<<"$html"
grep -q 'Every observation lands as readable notes' <<<"$html"
grep -q 'Obsidian' <<<"$html"
grep -q 'Together they turn scattered signals into unique and actionable insights' <<<"$html"
# Connectors perf: no multi-layer SVG drop-shadow on push glow; pause wiring present
! grep -q 'drop-shadow(0 0 48px rgba(74, 222, 128' index.html
grep -q 'is-flow-paused' index.html
grep -q 'animation-play-state: paused' index.html
grep -q 'Self-hosted, readable, and under your control\.' <<<"$html"
[[ "$(grep -o '<h3>' <<<"$html" | wc -l | tr -d ' ')" -eq 4 ]]
grep -q '<h3>The Problem</h3>' <<<"$html"
grep -q 'Pulse runs on your hardware' <<<"$html"
grep -q '<h3>The Reclamation</h3>' <<<"$html"
grep -q 'Same data\. Different agenda\.' <<<"$html"
grep -q '<h3>Sovereignty</h3>' <<<"$html"
grep -q 'Every insight, every memory' <<<"$html"
! grep -q '<h3>On Your Terms</h3>' <<<"$html"
! grep -q '<form' <<<"$html"
! grep -q 'formspree.io' <<<"$html"
grep -q 'Install now' <<<"$html"
grep -q 'curl -fsSL https://pulseagent.dev/install.sh | bash' <<<"$html"
grep -q 'class="install-code"' <<<"$html"
grep -q 'class="install-docs"' <<<"$html"
grep -q 'View documentation' <<<"$html"
! grep -q 'Join the early access list' <<<"$html"
! grep -q 'Request Early Access' <<<"$html"
! grep -q 'Notify Me' <<<"$html"
! grep -q 'This is being built in the open\.' <<<"$html"
! grep -q 'In development' <<<"$html"

grep -q '<title>Pulse Docs</title>' <<<"$docs_bridge_html"
assert_contains "$docs_html" 'Pulse Docs'
assert_contains "$docs_html" 'What is Pulse?'
assert_contains "$docs_html" 'Quick Start'
assert_contains "$docs_html" 'Run Pulse'
assert_contains "$docs_html" 'Configure Pulse'
assert_contains "$docs_html" 'Operate Pulse'
assert_contains "$docs_html" 'Connect Data Sources'
assert_contains "$docs_html" 'Self-Hosting'
assert_contains "$docs_html" 'Configuration'
assert_contains "$docs_html" 'Operations'
assert_contains "$docs_html" 'Connectors'
assert_contains "$docs_html" 'Self-Hosting Quickstart'
assert_contains "$docs_html" 'pulse-home-card'
assert_contains "$docs_html" 'Open quickstart'
assert_contains "$docs_html" 'What is Pulse?'
assert_contains "$quickstart_html" 'Self-Hosting Quickstart'
assert_contains "$quickstart_html" 'pulse configure'
assert_contains "$quickstart_html" 'Manual install (if you already use pipx):'
assert_contains "$quickstart_html" 'pulseagent.dev/install.sh'
assert_contains "$quickstart_html" 'docker build'
assert_contains "$install_sh_body" '#!/usr/bin/env bash'
assert_contains "$install_sh_body" 'pulse-agent'
assert_contains "$install_sh_body" 'pipx'
assert_contains "$configuration_html" 'Configuration Reference'
assert_contains "$configuration_html" 'PULSE_DATABASE_PATH'
assert_contains "$configuration_html" 'Top-level fields'
assert_contains "$runbook_html" 'Operations Runbook'
assert_contains "$runbook_html" 'GET /health'
assert_contains "$runbook_html" 'Triage'
assert_contains "$connectors_html" 'Connectors Index'
assert_contains "$connectors_html" 'plaid_tokens.json'
assert_contains "$connectors_html" 'Google'
