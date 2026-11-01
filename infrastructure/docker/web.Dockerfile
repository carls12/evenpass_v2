# Builds all static frontends and serves them with Caddy (also the reverse proxy).
# Build context: repository root.

FROM node:22-alpine AS portal
WORKDIR /build
COPY apps/portal/package.json apps/portal/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/portal/ ./
# Public contact details are compiled into the site (see apps/portal/.env.example).
ARG VITE_CONTACT_EMAIL=""
ARG VITE_CONTACT_PHONE=""
ARG VITE_CONTACT_ADDRESS=""
ARG VITE_ORGANISATION_NAME="CMGI"
RUN npm run build

FROM node:22-alpine AS eventpass
WORKDIR /build
COPY apps/eventpass/frontend/package.json apps/eventpass/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/eventpass/frontend/ ./
RUN npm run build

FROM node:22-alpine AS sermon
WORKDIR /build
COPY apps/sermon-ai/frontend/package.json apps/sermon-ai/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/sermon-ai/frontend/ ./
RUN npm run build

FROM caddy:2.8-alpine
COPY infrastructure/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=portal /build/dist /srv/portal
COPY --from=eventpass /build/dist /srv/eventpass
COPY --from=sermon /build/dist /srv/sermon-ai
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO /dev/null http://127.0.0.1:2019/config/ || exit 1
