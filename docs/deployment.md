# Deployment Guide

This guide covers different ways to deploy Plugo in production.

## Table of Contents

- [Docker Compose (Recommended)](#docker-compose-recommended)
- [Manual Deployment](#manual-deployment)
- [Environment Variables](#environment-variables)
- [Reverse Proxy (Nginx)](#reverse-proxy-nginx)
- [SSL/HTTPS Setup](#sslhttps-setup)
- [Production Checklist](#production-checklist)

## Docker Compose (Recommended)

The simplest way to deploy Plugo is with Docker Compose.

### 1. Clone and configure

```bash
git clone https://github.com/stop1love1/plugo.git
cd plugo
cp .env.example .env
```

### 2. Edit environment variables

```bash
# .env - Production settings
LLM_PROVIDER=claude
LLM_MODEL=claude-sonnet-4-20250514
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Use MongoDB for production
DATABASE_PROVIDER=mongodb

# Security
SECRET_KEY=your-random-secret-key-here
CORS_ORIGINS=https://yourdomain.com,https://dashboard.yourdomain.com

# Embedding
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
```

### 3. Start services

```bash
docker compose up -d
```

Services will be available at:
- Backend API: `http://localhost:8000`
- Dashboard: `http://localhost:3000`
- API Docs: `http://localhost:8000/docs`

### 4. Verify

```bash
# Check all services are running
docker compose ps

# Check backend health
curl http://localhost:8000/health
```

## Manual Deployment

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start with production server
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Dashboard

```bash
cd dashboard
npm install
npm run build
# Serve the dist/ folder with any static file server (nginx, caddy, etc.)
```

### Widget

```bash
cd widget
npm install
npm run build
# The output (widget.js) should be served by the backend at /static/widget.js
# Copy dist/ contents to backend's static directory
```

## Environment Variables

See [.env.example](../.env.example) for all available variables.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_PROVIDER` | No | `claude` | LLM provider: `claude`, `openai`, `gemini`, `ollama` |
| `LLM_MODEL` | No | `claude-sonnet-4-20250514` | Model identifier |
| `ANTHROPIC_API_KEY` | Yes* | — | Anthropic API key (*if using Claude) |
| `OPENAI_API_KEY` | Yes* | — | OpenAI API key (*if using OpenAI/embeddings) |
| `GEMINI_API_KEY` | Yes* | — | Google Gemini API key (*if using Gemini) |
| `DATABASE_PROVIDER` | No | `sqlite` | Database: `sqlite` or `mongodb` |
| `MONGODB_URL` | No | `mongodb://localhost:27017` | MongoDB connection string |
| `EMBEDDING_PROVIDER` | No | `openai` | Embedding provider: `openai` or `ollama` |
| `SECRET_KEY` | Yes | `change-me` | Secret key for token generation |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Allowed CORS origins (comma-separated) |

## Reverse Proxy (Nginx)

Example Nginx configuration for production:

```nginx
# Backend API + WebSocket
server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support
    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Serve widget.js with caching
    location /static/ {
        proxy_pass http://localhost:8000;
        proxy_cache_valid 200 1h;
        add_header Cache-Control "public, max-age=3600";
    }
}

# Dashboard
server {
    listen 443 ssl;
    server_name dashboard.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/dashboard.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dashboard.yourdomain.com/privkey.pem;

    root /var/www/plugo-dashboard/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

## SSL/HTTPS Setup

For production, you should use HTTPS. The easiest way is with Let's Encrypt:

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificates
sudo certbot --nginx -d api.yourdomain.com -d dashboard.yourdomain.com
```

Update your widget embed code to use `wss://` instead of `ws://`:

```html
<script>
  window.PlugoConfig = {
    token: "YOUR_SITE_TOKEN",
    serverUrl: "wss://api.yourdomain.com",
  };
</script>
<script src="https://api.yourdomain.com/static/widget.js" async></script>
```

## Production Checklist

Before going live, ensure:

- [ ] **Security**
  - [ ] `SECRET_KEY` is set to a strong random value
  - [ ] `CORS_ORIGINS` is restricted to your domains only
  - [ ] API keys are not exposed in client-side code
  - [ ] HTTPS is enabled for all endpoints

- [ ] **Database**
  - [ ] MongoDB is used for production (not SQLite)
  - [ ] Database backups are configured
  - [ ] MongoDB authentication is enabled

- [ ] **Performance**
  - [ ] Backend runs with multiple workers (`--workers 4`)
  - [ ] Static assets are served with caching headers
  - [ ] Widget JS is minified (automatic via Vite build)

- [ ] **Monitoring**
  - [ ] Health check endpoint (`/health`) is monitored
  - [ ] Error logging is configured
  - [ ] Docker container restart policies are set

- [ ] **Widget**
  - [ ] Widget loads correctly on target websites
  - [ ] WebSocket connection is stable
  - [ ] Chat responses are streaming properly
