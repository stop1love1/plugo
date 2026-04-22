FROM node:20-slim AS build

RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml* .
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# Production stage — serve static files with a lightweight server
FROM node:20-slim

RUN npm install -g serve && \
    groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

COPY --from=build --chown=appuser:appuser /app/dist /app/dist

USER appuser

EXPOSE 3000

CMD ["serve", "-s", "/app/dist", "-l", "3000"]
