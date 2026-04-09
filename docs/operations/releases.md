# Releases and versioning

- **PyPI package:** `pulse-agent` (CLI entry points `pulse` and `pulse-mcp`).
- **Versioning:** [Semantic Versioning](https://semver.org/) — **MAJOR** for incompatible changes (including config or behavior you must act on), **MINOR** for backward-compatible features, **PATCH** for fixes. Review **`CHANGELOG.md`** before upgrading.
- **Shipping:** push a git tag `v*` (for example `v1.0.0`). CI builds, publishes to PyPI, and builds Docker per [`.github/workflows/release-publish.yml`](https://github.com/JEFF7712/pulse/blob/main/.github/workflows/release-publish.yml). Copy **`CHANGELOG.md`** into the GitHub release notes for that tag.

PyPI trusted publishing details: [PyPI trusted publishing](./pypi-trusted-publishing.md).
