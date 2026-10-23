# Sahayak

**Sahayak** is a modular, stateless, voice-first AI assistant delivered as an [Alexa+ Model Context Protocol (MCP)](https://modelcontextprotocol.io) add-on.

It empowers learners and knowledge seekers to quiz themselves on any topic, study spaced repetition flashcards (SuperMemo-2), schedule exam preparation plans, track study streaks, and retrieve fact-checked topic overviews—completely hands-free.

---

## Architecture Highlights

- **Stateless HTTP Transport:** Implements MCP Streamable HTTP on `/mcp`. Holds zero in-memory session state; state handles are serialized in responses.
- **Layered Clean Architecture:** Modules follow `tools -> service -> domain` separation. Domain logic imports no frameworks or I/O.
- **Cross-Module Boundaries:** Modules interact strictly via declared `api.py` protocols or transactional outbox events.
- **Grounding & Safety:** LLM question generation and topic briefs are strictly grounded in retrieved educational sources (Wikipedia), validated through multi-pass verification, and sanitized against prompt injections.
- **Voice UX Compliance:** Voice summaries strictly conform to $\le 300$ characters, conceal answers during questions, and strip raw markdown formatting and URLs.
- **GDPR / Privacy Native:** Full cascading user data export and deletion (Right to be Forgotten) across all schemas.

---

## Quick Start

### 1. Prerequisites
- Python 3.12+
- Docker and Docker Compose
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 18+ (optional, for `@modelcontextprotocol/inspector`)

### 2. Setup Environment
```bash
# Clone the repository
git clone https://github.com/prateekg7/sahayak.git
cd sahayak

# Install dependencies and pre-commit hooks
make setup

# Copy environment variables
cp .env.example .env
```

### 3. Run Locally with Docker Compose
```bash
make dev
```
This boots:
- **FastAPI MCP Server** on `http://localhost:8000`
- **Background Worker (Arq)** processing outbox events and question pre-generation
- **PostgreSQL 16** on port 5432
- **Redis 7** on port 6379

Verify the server is healthy:
```bash
curl -i http://localhost:8000/healthz
```

---

## Development & Quality Gates

Run all quality gates locally before pushing code:

```bash
make lint            # ruff check/format, mypy --strict, import-linter contracts
make test            # unit, integration, and Streamable HTTP contract tests (>= 85% coverage)
make snapshot-check  # verifies public MCP tool signatures match snapshot
make migrate-check   # tests expand-only migrations up -> down -> up
make security        # bandit AST scanner and pip-audit vulnerability audit
```

---

## Interactive MCP Debugging

Inspect and invoke MCP tools locally using the official MCP Inspector:
```bash
make inspector
# Opens interactive UI targeting http://localhost:8000/mcp
```

Or expose the server publicly for Alexa+ developer testing:
```bash
make tunnel
# Starts Cloudflare tunnel targeting http://localhost:8000
```

---

## Developer Guides

- [Developer Guide](file:///docs/dev-guide.md): In-depth setup, debugging, migrations, and testing workflows.
- [Module Authoring Guide](file:///docs/module-authoring.md): Step-by-step guide to adding new capability modules from `_template`.
- [Architecture Deep-Dive](file:///docs/architecture.md): Layering, events, database schemas, and voice guidelines.
- [Contributing](file:///CONTRIBUTING.md): Contribution rules, coding standards, and commit conventions.
