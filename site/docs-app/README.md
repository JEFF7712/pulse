## Pulse docs app

Run the VitePress docs locally from `site/docs-app`.

The markdown under `site/docs-app/docs/` is intentionally thin. The main published pages render the canonical repo docs from `docs/` via VitePress includes, so edit `docs/` first when you are changing content.

The repo `docs/` tree is authoritative for published documentation content.

When you add a new published markdown page under `docs/`, add a matching wrapper page under `site/docs-app/docs/`.

Each wrapper should stay thin: identify the canonical repo doc and include it directly via a VitePress include.

### Install dependencies

```bash
npm ci
```

### Start the local docs server

```bash
npm run docs:dev
```

The dev server binds to `0.0.0.0` and serves the site at `/docs/`.

### Build the docs

```bash
npm run docs:build
```

The production output is written to `docs/.vitepress/dist/`.

### Build the docs container

Build from the repository root so Docker can see both `docs/` and `site/docs-app/`:

```bash
docker build -f site/Dockerfile -t pulse-site .
```

### Preview the production build

```bash
npm run docs:preview
```
