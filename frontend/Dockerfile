# syntax=docker/dockerfile:1

# ---- build the SPA ----------------------------------------------------------
FROM node:20-bookworm-slim AS builder

ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    HUSKY=0 \
    CI=1

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# ---- serve with nginx -----------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
