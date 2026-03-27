<p align="center">
  <img src="logo.png" alt="Plugo" width="120" />
</p>

<h1 align="center">Plugo</h1>

<p align="center">
  <strong>Plug an AI assistant into any platform — with a single script tag</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License" /></a>
  <a href="https://github.com/stop1love1/plugo/actions"><img src="https://github.com/stop1love1/plugo/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python" />
  <img src="https://img.shields.io/badge/node-18+-green.svg" alt="Node.js" />
</p>

<p align="center">
  Plugo turns any website, web app, or platform into an AI-powered system.<br/>
  Customers interact through a single chat window to understand your product,<br/>
  look up information, and take actions — the bot calls your APIs on their behalf.<br/>
  Self-hosted, open source, multi-LLM support.
</p>

---

## Features

- **One Script Tag** — Embed a chat widget on any website in seconds
- **Auto-Learn from Website** — Crawls your site and answers questions based on your content
- **API Actions** — Bot can call your APIs to perform real actions (search products, place orders, etc.)
- **Multi-LLM** — Supports Claude, GPT-4o, Gemini, and Ollama (local models)
- **Real-time Streaming** — Responses stream token-by-token via WebSocket
- **Self-Hosted** — MIT license, deploy anywhere, keep your data

---

## Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/stop1love1/plugo.git
cd plugo
cp .env.example .env
# Add your API keys to .env
```

### 2. Run with Docker

```bash
docker compose up --build
```

| Service       | URL                         |
| ------------- | --------------------------- |
| Dashboard     | http://localhost:3000        |
| Backend API   | http://localhost:8000        |
| API Docs      | http://localhost:8000/docs   |

### 3. Embed on Your Website

```html
<script>
  window.PlugoConfig = {
    token: "YOUR_SITE_TOKEN",
    serverUrl: "ws://localhost:8000",
    primaryColor: "#6366f1",
    greeting: "Hi! How can I help you?"
  };
</script>
<script src="http://localhost:8000/static/widget.js" async></script>
```

Paste this code before the `</body>` tag. The widget loads asynchronously and appears after the page loads.

---

## How It Works

```
Website visitor types a message
  → Widget sends via WebSocket
  → Backend retrieves relevant content (RAG)
  → LLM generates a response
  → Response streams back to the widget in real time
```

The bot operates in two modes:

| Mode | Description |
|------|-------------|
| **Knowledge Mode** | Answers questions using crawled website content and uploaded documents |
| **Action Mode** | Calls external APIs to perform actions on behalf of users (search, order, register, etc.) |

---

## Dashboard

The dashboard is the admin interface where you manage everything about your AI assistant.

### Sites

Manage all your connected websites. Each site gets its own configuration, knowledge base, tools, and chat history.

- Create a new site by entering a name and URL
- Each site receives a unique token for embedding
- All settings below are configured per-site

### Knowledge Base

The knowledge base is the content your bot uses to answer questions. There are three ways to add content:

| Method | Description |
|--------|-------------|
| **Website Crawling** | Automatically crawl your website and extract content (see Setup below) |
| **File Upload** | Upload `.txt` or `.md` files |
| **Manual Entry** | Type a title and content directly |

Each piece of content is split into chunks, converted to vector embeddings, and stored for semantic search. When a visitor asks a question, the system finds the top 5 most relevant chunks and provides them as context to the LLM.

### Setup (Crawling)

Configure automatic website crawling to populate your knowledge base.

- **Toggle crawling** on/off per site
- **Max pages**: Set crawl depth from 1 to 500 pages (default: 50)
- **Custom URL**: Override the default site URL to crawl specific sections
- **Start/Stop**: Manually trigger or halt a crawl at any time
- **Clear all knowledge**: Remove all learned data and start fresh
- **Crawl history**: View past crawl jobs with status, page count, and timestamps

Crawl statuses: `idle` → `running` → `completed` / `failed` / `stopped`

### Tools (API Actions)

Configure API endpoints that your bot can call during conversations. This enables the bot to perform real actions, not just answer questions.

Each tool requires:

| Field | Description |
|-------|-------------|
| **Name** | Identifier (e.g., `search_products`) |
| **Description** | Tells the bot when to use this tool |
| **Method** | GET, POST, PUT, or DELETE |
| **URL** | The API endpoint |
| **Auth Type** | None, Bearer Token, API Key, or Basic Auth |
| **Params Schema** | JSON schema defining what parameters the tool accepts |

**Example use cases:**
- Search products by name or category
- Place orders or reservations
- Register user accounts
- Look up order status
- Any HTTP-based action your backend supports

You can test each tool directly from the dashboard before going live.

### Chat Log

Monitor all conversations between visitors and your bot.

- View all chat sessions with message counts and timestamps
- Click any session to see the full conversation
- User messages and bot responses are displayed with timestamps
- Useful for monitoring quality, identifying common questions, and improving your knowledge base

### Settings

Configure your site's AI provider and widget appearance.

**LLM Provider:**

| Provider | Models | Requirement |
|----------|--------|-------------|
| **Claude** (Anthropic) | Sonnet 4, Opus 4, Haiku 3.5 | `ANTHROPIC_API_KEY` |
| **OpenAI** | GPT-4o, GPT-4o Mini | `OPENAI_API_KEY` |
| **Gemini** (Google) | Gemini 1.5 Flash, Gemini 1.5 Pro | `GEMINI_API_KEY` |
| **Ollama** (Local) | Llama 3, Mistral 7B | `OLLAMA_BASE_URL` |

Each site can use a different provider and model.

**Widget Appearance:**

| Setting | Description | Default |
|---------|-------------|---------|
| Primary Color | Theme color (hex) for the widget | `#6366f1` |
| Position | `bottom-right` or `bottom-left` | `bottom-right` |
| Greeting | Welcome message when chat opens | `Hello! How can I help you?` |

**Security:**

- **Domain Whitelist** — Comma-separated list of domains allowed to embed the widget. Leave blank to allow all domains.

### Embed

Get the embed code for your website. Two versions are provided:

- **Development** — Points to `localhost:8000` for local testing
- **Production** — Points to `https://cdn.plugo.dev/widget.js` for live sites

One-click copy for both versions.

---

## Widget

The widget is a lightweight (~50KB) chat interface that appears on your website.

**Visitor experience:**
- Floating chat button in the bottom corner of the page
- Click to open a chat window with your greeting message
- Type questions and receive streaming responses in real-time
- Bot answers based on your knowledge base and configured tools
- Responds in the visitor's language automatically

**Page context awareness:**
The widget automatically sends the current page URL, title, and visible text (first 1500 characters) to the bot, so responses are relevant to what the visitor is currently viewing.

**Widget configuration options:**

```js
window.PlugoConfig = {
  token: "your-site-token",       // Required — authenticates the widget
  serverUrl: "ws://localhost:8000", // Optional — backend WebSocket URL
  primaryColor: "#6366f1",         // Optional — theme color
  greeting: "Hi! How can I help?", // Optional — welcome message
  position: "bottom-right"         // Optional — "bottom-right" or "bottom-left"
};
```

---

## Environment Configuration

All configuration is done via the `.env` file. Copy `.env.example` to get started.

### LLM

```env
LLM_PROVIDER=claude                      # claude | openai | gemini | ollama
LLM_MODEL=claude-sonnet-4-20250514       # Default model
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434
```

### Embeddings (for knowledge search)

```env
EMBEDDING_PROVIDER=openai                # openai | ollama
EMBEDDING_MODEL=text-embedding-3-small
```

### Database

```env
DATABASE_PROVIDER=sqlite                 # sqlite | mongodb
DATABASE_URL=sqlite:///./data/plugo.db

# MongoDB (optional)
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=plugo
```

### Vector Store

```env
CHROMA_PATH=./data/chroma
```

### Security & Server

```env
SECRET_KEY=change-me-to-a-random-string
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
BACKEND_PORT=8000
DASHBOARD_PORT=3000
```

---

## API Reference

Full interactive API documentation (Swagger UI): **http://localhost:8000/docs**

---

## Development

```bash
make setup          # One-time: create venv, install all deps
make dev            # Start all 3 services concurrently
make test           # Run all tests
make lint           # Run all linters
make format         # Format all code
make check          # Run lint + format-check + typecheck
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## Security

If you discover a security vulnerability, please report it responsibly. See [SECURITY.md](SECURITY.md) for details.

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.
