FROM node:20-slim AS build

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml* .
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# Production stage — serve static files with a lightweight server
FROM node:20-slim

RUN npm install -g serve

COPY --from=build /app/dist /app/dist

EXPOSE 3000

CMD ["serve", "-s", "/app/dist", "-l", "3000"]
