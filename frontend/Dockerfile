# ================================================================
# InfraGenie Frontend — Dockerfile
# Node 18 Alpine image running Create React App dev server.
# For production, swap CMD with `npm run build` + nginx.
# ================================================================

FROM node:18-alpine

LABEL maintainer="infragenie"
LABEL description="InfraGenie React frontend (CRA dev server)"

# ── System deps (needed by some native npm packages) ───────────
RUN apk add --no-cache libc6-compat

WORKDIR /app

# ── Install dependencies first (cache-friendly layer) ─────────
COPY package.json package-lock.json* ./
RUN npm ci --legacy-peer-deps

# ── Copy source ────────────────────────────────────────────────
COPY . .

# ── Port ──────────────────────────────────────────────────────
EXPOSE 3000

# ── CRA needs this to avoid interactive prompts ────────────────
ENV CI=false
ENV CHOKIDAR_USEPOLLING=true

# ── Start dev server ──────────────────────────────────────────
CMD ["npm", "start"]
