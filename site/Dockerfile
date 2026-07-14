FROM node:24-alpine AS docs-builder

WORKDIR /app/site/docs-app

COPY site/docs-app/package.json site/docs-app/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

COPY site/docs-app/ ./
COPY docs/ /app/docs/
RUN npm run docs:build

FROM nginx:alpine

COPY site/nginx.conf /etc/nginx/nginx.conf
COPY site/index.html /usr/share/nginx/html/index.html
COPY scripts/install.sh /usr/share/nginx/html/install.sh
COPY site/pulse-mark.svg /usr/share/nginx/html/pulse-mark.svg
COPY --from=docs-builder /app/site/docs-app/docs/.vitepress/dist/favicon.ico /usr/share/nginx/html/favicon.ico
COPY --from=docs-builder /app/site/docs-app/docs/.vitepress/dist/ /usr/share/nginx/html/docs/

EXPOSE 8080

USER 101:101
