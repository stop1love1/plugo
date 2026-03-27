# Contributing to Plugo

Thank you for your interest in contributing to Plugo! This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/plugo.git
   cd plugo
   ```
3. **Add upstream** remote:
   ```bash
   git remote add upstream https://github.com/stop1love1/plugo.git
   ```
4. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (optional, for full-stack dev)

### Option 1: Docker (recommended)

```bash
cp .env.example .env
# Fill in your API keys in .env
docker compose up --build
```

### Option 2: Manual Setup

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload

# Dashboard (new terminal)
cd dashboard
npm install
npm run dev

# Widget (new terminal)
cd widget
npm install
npm run build
```

See [docs/development.md](docs/development.md) for detailed setup instructions.

## Project Structure

```
plugo/
├── backend/          # FastAPI backend (Python)
│   ├── agent/        # LLM agent, RAG, tool executor
│   ├── knowledge/    # Crawler, vector store
│   ├── models/       # Database models
│   ├── providers/    # Multi-LLM providers
│   ├── repositories/ # Data access layer
│   └── routers/      # API endpoints
├── widget/           # Embeddable chat widget (Preact)
├── dashboard/        # Management UI (React)
├── docs/             # Documentation
└── examples/         # Usage examples
```

## Making Changes

1. **Sync** your fork with upstream before starting:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Make your changes** in a feature branch

3. **Test your changes** locally:
   - Backend: ensure the API starts without errors
   - Widget: run `npm run build` and verify the output
   - Dashboard: run `npm run dev` and test in the browser

4. **Commit** with a clear message:
   ```bash
   git commit -m "feat: add support for custom widget themes"
   ```

### Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/). This is **enforced by a pre-commit hook** — commits that don't follow this format will be rejected.

Format: `<type>(<optional scope>): <description>`

| Prefix      | Description                          |
|-------------|--------------------------------------|
| `feat:`     | New feature                          |
| `fix:`      | Bug fix                              |
| `docs:`     | Documentation changes                |
| `style:`    | Code style (formatting, no logic)    |
| `refactor:` | Code refactoring                     |
| `test:`     | Adding or updating tests             |
| `chore:`    | Build process, dependencies, tooling |
| `ci:`       | CI/CD configuration                  |
| `perf:`     | Performance improvement              |
| `build:`    | Build system changes                 |
| `revert:`   | Revert a previous commit             |

Examples:
```
feat: add dark mode toggle to dashboard
fix(widget): prevent XSS in message rendering
docs: update deployment guide with SSL setup
refactor(backend): extract auth middleware
test: add integration tests for crawl router
ci: add test coverage reporting to GitHub Actions
perf(widget): lazy-load message history
```

Breaking changes should include `BREAKING CHANGE:` in the commit body or append `!` after the type:
```
feat!: replace REST chat endpoint with WebSocket-only
```

## Pull Request Process

1. **Push** your branch to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
2. **Open a Pull Request** against `main` branch
3. **Fill in** the PR template with:
   - Summary of changes
   - Related issue number (if any)
   - Screenshots (for UI changes)
4. **Wait for review** — maintainers will review and provide feedback
5. **Address feedback** and push updates to the same branch

### PR Requirements

- [ ] Code follows the project's coding standards
- [ ] Changes have been tested locally
- [ ] PR description clearly explains the changes
- [ ] No unnecessary files are included

## Coding Standards

### Python (Backend)

- Follow PEP 8
- Use type hints for function parameters and return values
- Use `async/await` for I/O operations
- Keep functions focused and small

### TypeScript (Widget & Dashboard)

- Use TypeScript strict mode
- Prefer functional components with hooks
- Use meaningful variable and function names
- Keep components small and reusable

### General

- No hardcoded secrets or API keys
- Write code that is easy to read and understand
- Add comments only where the logic is not self-evident

## Reporting Issues

### Bug Reports

When filing a bug report, include:

1. **Environment**: OS, Python version, Node.js version, browser
2. **Steps to reproduce**: Minimal steps to trigger the bug
3. **Expected behavior**: What should happen
4. **Actual behavior**: What actually happens
5. **Logs/Screenshots**: Any relevant error messages or screenshots

### Feature Requests

When requesting a feature, include:

1. **Problem**: What problem does this solve?
2. **Proposed solution**: How do you envision it working?
3. **Alternatives considered**: Other approaches you've thought of

---

Thank you for contributing to Plugo!
