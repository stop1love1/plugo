# Plugo

**Embeddable AI Chat Widget** — Cho phép bất kỳ website nào thêm trợ lý AI thông minh chỉ bằng 3 dòng code.

## Features

- **Dán 1 script tag** — Widget chat tự động xuất hiện trên website
- **Tự crawl nội dung** — Bot tự học từ website, trả lời chính xác
- **Gọi API website** — Bot thực hiện action thực tế (tìm sản phẩm, đặt hàng...)
- **Multi-LLM** — Hỗ trợ Claude, GPT-4o, Gemini, Ollama (local)
- **Self-host / Open source** — MIT license, chạy local hoặc deploy

## Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/stop1love1/plugo.git
cd plugo
cp .env.example .env
# Điền API key vào .env
```

### 2. Chạy với Docker

```bash
docker compose up
```

- Dashboard: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### 3. Chạy thủ công (cho dev)

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Dashboard (terminal khác)
cd dashboard
npm install
npm run dev

# Widget (terminal khác)
cd widget
npm install
npm run build
```

### 4. Embed vào website

```html
<script>
  window.PlugoConfig = {
    token: "YOUR_SITE_TOKEN",
    serverUrl: "ws://localhost:8000",
    primaryColor: "#6366f1",
    greeting: "Xin chào! Tôi có thể giúp gì?"
  };
</script>
<script src="http://localhost:8000/static/widget.js" async></script>
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python / FastAPI |
| Widget | TypeScript / Preact (~50KB) |
| Dashboard | React / Vite / Tailwind |
| Vector Store | ChromaDB |
| Database | SQLite → PostgreSQL |
| LLM | Claude / OpenAI / Gemini / Ollama |

## Architecture

```
plugo/
├── backend/          # FastAPI — Chat API, Crawler, Agent
│   ├── routers/      # API endpoints
│   ├── agent/        # LLM agent, RAG, tool executor
│   ├── knowledge/    # Crawler, vector store
│   ├── providers/    # Multi-LLM providers
│   └── models/       # Database models
├── widget/           # Preact — Embeddable chat widget
│   └── src/ui/       # Bubble, Window, Message components
├── dashboard/        # React — Management UI
│   └── src/pages/    # Setup, Knowledge, Tools, Embed, Settings
└── docker-compose.yml
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | `/ws/chat/{token}` | WebSocket chat streaming |
| POST | `/api/sites` | Create site |
| POST | `/api/crawl` | Start crawling |
| GET | `/api/knowledge` | List knowledge chunks |
| POST | `/api/tools` | Add API tool |
| GET | `/api/sessions` | Chat history |

## License

MIT
