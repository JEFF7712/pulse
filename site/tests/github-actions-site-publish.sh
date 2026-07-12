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
grep -q 'actions/checkout@v6' "$workflow"
grep -q 'docker/setup-buildx-action@v4' "$workflow"
grep -q '^  publish:$' "$workflow"
grep -q "github.event_name == 'push' && github.ref == 'refs/heads/main'" "$workflow"
grep -q 'docker/login-action@v4' "$workflow"
grep -q 'docker/metadata-action@v6' "$workflow"
grep -q 'docker/build-push-action@v7' "$workflow"
grep -q 'packages: write' "$workflow"
grep -q 'DOCKER_IMAGE: ghcr.io/jeff7712/pulse-site' "$workflow"
grep -q 'registry: ghcr.io' "$workflow"
grep -q 'username: ${{ github.actor }}' "$workflow"
grep -q 'password: ${{ secrets.GITHUB_TOKEN }}' "$workflow"
grep -q 'type=raw,value=0.0.${{ github.run_number }}' "$workflow"
grep -q '^          context: .$' "$workflow"
grep -q '^          file: ./site/Dockerfile$' "$workflow"
grep -q '^          push: true$' "$workflow"
