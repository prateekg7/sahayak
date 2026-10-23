# Contributing to Sahayak

Thank you for contributing to Sahayak! We hold our codebase to production-grade engineering standards: strict static typing, 85%+ test coverage, immutable module boundaries, and voice-safe UX design.

---

## 1. Non-Negotiable Rules

1. **Never Commit Secrets:** API keys, database passwords, and `.env` files must never enter version control.
2. **Never Import Across Module Boundaries:** Modules must never import directly from another module. All cross-module interactions happen via declared protocols in `api.py` or transactional outbox events.
3. **Never Put Business Logic in Tools:** MCP tools are thin adapters. They validate inputs, verify caller scopes, delegate to a service method, and return the standard JSON response envelope.
4. **Never Log PII or Health Data:** Sensitive user records, tokens, or prompt contents must be redacted.
5. **No Floating-Point Money:** Currency must always be represented as integer minor units (e.g. paisa, cents) with ISO currency codes.
6. **Statelessness:** Tools must never rely on transport session memory or in-memory process caches for dialogue state. State handles must be returned in response envelopes.

---

## 2. Development Workflow

1. **Pick a Task:** Review `tasks.md` and check prerequisites.
2. **Write Tests First:** Domain logic gets pure unit tests (and Hypothesis property tests where applicable); persistence layers get integration tests; tools get contract tests via the Streamable HTTP harness.
3. **Keep Gates Green:**
   ```bash
   make lint test snapshot-check migrate-check security
   ```
4. **Conventional Commits:**
   Use Conventional Commit formatting (`feat(...)`, `fix(...)`, `test(...)`, `docs(...)`) and reference the task ID in the commit body.

---

## 3. Pull Request & Review Checklist

Before requesting review, verify:
- [ ] `make lint` has 0 errors (ruff, mypy `--strict`, import-linter).
- [ ] `make test` passes with total line coverage $\ge 85\%$.
- [ ] Database migrations are expand-only and reversible (`make migrate-check`).
- [ ] Tool snapshots updated only if public tool interface changes were intentional.
- [ ] Spoken summaries adhere to $\le 300$ characters without raw markdown or URLs.
