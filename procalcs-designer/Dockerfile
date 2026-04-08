# syntax=docker/dockerfile:1.7
# Multi-stage build for procalcs-designer.
#   Stage 1 (builder): install all deps, build SPA (Vite → dist/) + server (esbuild → dist-server/)
#   Stage 2 (runtime): node:20-alpine with only dist/, dist-server/, and prod node_modules

FROM node:20-alpine AS builder
WORKDIR /app

# Install deps first (cache layer)
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

# Copy source and build both client and server
COPY tsconfig.json tsconfig.server.json vite.config.ts index.html components.json ./
COPY src ./src
COPY server ./server
RUN npm run build

# Prune dev deps so runtime image is small
RUN npm prune --omit=dev


FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8080

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/dist-server ./dist-server
COPY --from=builder /app/package.json ./package.json

EXPOSE 8080
CMD ["node", "dist-server/index.js"]
