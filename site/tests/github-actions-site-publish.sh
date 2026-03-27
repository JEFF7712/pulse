#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
workflow="$repo_root/.github/workflows/site-docker-publish.yml"

[[ -f "$workflow" ]]
grep -q '^name: Site Docker Publish$' "$workflow"
grep -q '^  pull_request:$' "$workflow"
grep -q '^  push:$' "$workflow"
grep -q "site/\\*\\*" "$workflow"
grep -q "\.github/workflows/site-docker-publish.yml" "$workflow"
grep -q '^jobs:$' "$workflow"
grep -q '^  smoke:$' "$workflow"
grep -q 'actions/checkout@v4' "$workflow"
grep -q 'docker/setup-buildx-action@v3' "$workflow"
grep -q 'bash tests/static-site-smoke.sh' "$workflow"
grep -q '^  publish:$' "$workflow"
grep -q '^    needs: smoke$' "$workflow"
grep -q "github.event_name == 'push' && github.ref == 'refs/heads/main'" "$workflow"
grep -q 'docker/login-action@v3' "$workflow"
grep -q 'docker/metadata-action@v5' "$workflow"
grep -q 'docker/build-push-action@v6' "$workflow"
grep -q 'DOCKERHUB_USERNAME' "$workflow"
grep -q 'DOCKERHUB_TOKEN' "$workflow"
grep -q 'type=raw,value=latest' "$workflow"
grep -q 'type=sha,prefix=sha-' "$workflow"
grep -q '^          context: .$' "$workflow"
grep -q '^          file: ./site/Dockerfile$' "$workflow"
grep -q '^          push: true$' "$workflow"
