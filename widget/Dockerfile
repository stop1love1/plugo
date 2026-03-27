FROM node:20-slim AS builder

WORKDIR /app

COPY package.json .
RUN npm install

COPY . .
RUN npm run build

# Output: /app/dist/widget.js
# Volume mount makes this file available to the backend for serving
