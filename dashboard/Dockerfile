FROM node:20-slim

WORKDIR /app

COPY package.json .
RUN npm install

COPY . .

EXPOSE 3000

# Vite dev server — proxies /api and /ws to the backend
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
