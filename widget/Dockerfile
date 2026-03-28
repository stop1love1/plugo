FROM node:20-slim AS builder

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml* .
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build

# Output: /app/dist/widget.js
# Volume mount makes this file available to the backend for serving
