FROM registry.rupan.dev/upstream/docker.io/library/node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS docs-builder

WORKDIR /app/site/docs-app

COPY site/docs-app/package.json site/docs-app/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

COPY site/docs-app/ ./
COPY docs/ /app/docs/
RUN npm run docs:build

FROM registry.rupan.dev/upstream/docker.io/library/nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de

COPY site/nginx.conf /etc/nginx/nginx.conf
COPY site/index.html /usr/share/nginx/html/index.html
COPY scripts/install.sh /usr/share/nginx/html/install.sh
COPY site/pulse-mark.svg /usr/share/nginx/html/pulse-mark.svg
COPY --from=docs-builder /app/site/docs-app/docs/.vitepress/dist/favicon.ico /usr/share/nginx/html/favicon.ico
COPY --from=docs-builder /app/site/docs-app/docs/.vitepress/dist/ /usr/share/nginx/html/docs/

EXPOSE 8080

USER 101:101
