FROM node:20-slim

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml* .
RUN pnpm install --frozen-lockfile

COPY . .

EXPOSE 3000

# Vite dev server — proxies /api and /ws to the backend
CMD ["pnpm", "run", "dev", "--", "--host", "0.0.0.0"]
