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
  Add a smart chat widget to your website so visitors can ask questions,<br/>
  get instant answers from your content, and take actions like searching products<br/>
  or placing orders — all through a single conversation window.<br/>
  Self-hosted, open source, works with Claude, GPT, Gemini, or local models.
</p>

---

## What Can Plugo Do?

**For your visitors:**
- Ask questions and get instant answers based on your website content
- Perform actions like searching products, placing orders, or checking status — through chat
- Get responses in their own language, automatically
- Receive answers relevant to the page they're currently viewing

**For you:**
- Manage everything from a simple admin dashboard — no coding needed after setup
- See what visitors are asking, what the bot can't answer, and which tools are used most
- Add knowledge by crawling your website, uploading files, or typing content manually
- Connect any API so the bot can take real actions on behalf of visitors

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/stop1love1/plugo.git
cd plugo
make setup
```

`make setup` automatically creates the environment and installs all dependencies.

### 2. Add Your API Key

Open `.env` and fill in the key for the AI provider you want to use:

```env
ANTHROPIC_API_KEY=sk-ant-...    # For Claude
OPENAI_API_KEY=sk-...           # For GPT
GEMINI_API_KEY=...              # For Gemini
SECRET_KEY=any-random-string    # Change this to something unique
```

You only need one provider key — not all of them.

### 3. Create Admin Account

```bash
cd backend
python manage.py create-admin -u admin -p yourpassword
```

### 4. Start

```bash
make dev
```

Open your browser:

| Page | URL |
|------|-----|
| Admin Dashboard | http://localhost:3000 |
| API Docs | http://localhost:8000/docs |

### 5. Run with Docker (Optional)

```bash
cp .env.example .env
# Add your API key to .env
docker compose up --build
```

---

## How It Works

```
Visitor types a message
  → Widget sends it to the backend
  → Backend searches your knowledge base for relevant content
  → AI generates a response using that context
  → Response streams back to the visitor in real time
```

The bot works in two modes:

| Mode | What it does |
|------|-------------|
| **Answer questions** | Uses your website content, uploaded files, and manual entries to respond |
| **Take actions** | Calls your APIs to do things like search, order, register, look up status, etc. |

---

## Dashboard Guide

### Sites

Each website you connect is a "site" with its own settings, knowledge, tools, and chat history.

- Create a site by entering a name and URL
- Each site gets a unique token for embedding the widget

### Knowledge Base

This is the content your bot uses to answer questions. Three ways to add:

| Method | Description |
|--------|-------------|
| **Crawl website** | Automatically scan your website and extract content |
| **Upload files** | Upload `.txt` or `.md` files |
| **Manual entry** | Type a title and content directly |

### Crawl Settings

- Turn crawling on/off per site
- Set max pages to crawl (1–500, default 50)
- Start or stop a crawl at any time
- Clear all knowledge to start fresh
- View crawl history with status and page counts

### Tools (API Actions)

Connect API endpoints so your bot can take real actions during conversations.

**Examples:**
- Search products by name or category
- Place orders or reservations
- Look up order status
- Register user accounts
- Any action your backend supports via HTTP

You can test each tool directly from the dashboard before going live.

### Chat Log

- Browse all chat sessions with message counts and timestamps
- Click any session to read the full conversation
- Leave feedback on sessions

### Visitor Memory

The bot automatically remembers facts about returning visitors across conversations.

- View all visitors and what the bot has learned about them
- Edit or delete individual memories
- Clear all memories for a specific visitor

### Analytics

| Metric | What it shows |
|--------|--------------|
| Overview | Total sessions, messages, key numbers |
| Messages per day | Daily message volume chart |
| Popular questions | Most frequently asked questions |
| Knowledge gaps | Questions the bot struggled to answer |
| Tool usage | Which API tools are used most |

### Settings

**AI Provider** — each site can use a different provider and model:

| Provider | Requirement |
|----------|-------------|
| **Claude** (Anthropic) | `ANTHROPIC_API_KEY` |
| **OpenAI** (GPT-4o) | `OPENAI_API_KEY` |
| **Gemini** (Google) | `GEMINI_API_KEY` |
| **Ollama** (Local) | Install Ollama on your machine |

API keys can also be managed from the dashboard under **LLM Keys** — no need to edit `.env`.

**Widget appearance:**

| Setting | Default |
|---------|---------|
| Primary color (hex) | `#6366f1` |
| Position | Bottom-right |
| Greeting message | `Hello! How can I help you?` |

**Security:**
- Domain whitelist — only allow specific domains to embed the widget. Leave blank to allow all.

---

## Embedding the Widget

```html
<script>
  window.PlugoConfig = {
    token: "YOUR-SITE-TOKEN",
    serverUrl: "ws://localhost:8000",
    primaryColor: "#6366f1",
    greeting: "Hi! How can I help you?"
  };
</script>
<script src="http://localhost:8000/static/widget.js" async></script>
```

Paste this before the `</body>` tag. The widget loads in the background and appears after the page is ready.

The widget automatically sends the current page URL and title to the bot, so answers are relevant to what the visitor is viewing.

---

## Account Management

Admin accounts are managed via the command line:

```bash
cd backend

# Create admin
python manage.py create-admin -u admin -p yourpassword

# Reset password
python manage.py reset-password -u admin -p newpassword

# List all users
python manage.py list-users
```

---

## Development

```bash
make setup          # First-time setup (venv + deps + .env)
make dev            # Start all services
make test           # Run all tests
make lint           # Run linters
make format         # Format code
make check          # Lint + format-check + typecheck
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## Security

If you find a security vulnerability, please report it responsibly. See [SECURITY.md](SECURITY.md).

## License

MIT License — see [LICENSE](LICENSE).
