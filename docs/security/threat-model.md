# Sahayak STRIDE Security Threat Model

This document outlines the security architecture and threat modeling for **Sahayak** following the **STRIDE** methodology (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) per tasks.md T4.8.

---

## 1. System Overview & Trust Boundaries

Sahayak consists of:
- **Clients:** Amazon Alexa+ Voice Assistant (Cloud) and Local MCP Inspector.
- **Ingress:** AWS Application Load Balancer terminating TLS $\rightarrow$ ECS Fargate containers running FastAPI Streamable HTTP on `/mcp`.
- **Identity Provider:** AWS Cognito / Auth0 issuing signed RS256 JWTs with audience `sahayak-api`.
- **Data Stores:** PostgreSQL 16 (AWS RDS, KMS encrypted, private subnet), Redis 7 (ElastiCache, TLS encrypted).
- **Outbound Services:** Google Gemini / Groq APIs (TLS), Wikipedia API (TLS, host allow-list).

---

## 2. STRIDE Threat Analysis & Mitigations

### 2.1 Spoofing (Identity & Caller Authenticity)
- **Threat:** Malicious caller pretends to be Alexa+ or another user.
- **Mitigation:**
  - Strict JWT validation: signature verified via cached JWKS (`iss`, `aud`, `exp`, `nbf`, `alg=RS256`).
  - Account linking maps verified JWT `sub` to internal `user_id`.
  - The client cannot supply `user_id` in request payloads; `user_id` is extracted strictly from the verified principal context.
  - Anonymous callers are allowed only on declared public tools (`@allow_anonymous`); mutating and personal data tools strictly enforce `@requires()` with RFC 9728 `auth_required` challenges.

### 2.2 Tampering (Data Modification & Integrity)
- **Threat:** Modifying tool arguments, SQL injection, or prompt injection via Wikipedia / user input.
- **Mitigation:**
  - All input payloads validated via strict Pydantic v2 schemas with bounded lengths.
  - SQLAlchemy Core/ORM parameterized queries exclusively; zero string-concatenated SQL queries.
  - Wikipedia grounding text is treated as **data, not instructions**: strictly sanitized, HTML stripped, delimited with XML tags (`<source_extract>`), and instruct the LLM to ignore embedded instructions.
  - Idempotency layer (`@idempotent`) stores cryptographic hashes of requests and responses to prevent replay mutations.

### 2.3 Repudiation (Auditability)
- **Threat:** User or administrator denies performing an action.
- **Mitigation:**
  - `core.audit_log` records high-value actions (data export, data deletion, quiz completion) with hashed IP, timestamp, and action enum.
  - Transactional outbox pattern (`core.outbox_events`) provides an immutable, append-only domain event log.
  - Structlog emits JSON logs with trace and request correlation IDs.

### 2.4 Information Disclosure (Confidentiality & Privacy)
- **Threat:** Leaking PII, user quiz answers, database connection strings, or answers before voice prompt is completed.
- **Mitigation:**
  - Correct answers are strictly concealed from `quiz_start` payloads and question payloads.
  - Custom Structlog filter automatically redacts JWT tokens, passwords, API keys, and email addresses.
  - Zero stack traces or internal SQL error details exposed in MCP error envelopes; only standardized spoken error messages.
  - All databases, caches, and backups encrypted at rest with AWS KMS and in transit via TLS 1.3.

### 2.5 Denial of Service (Availability)
- **Threat:** Exhausting compute, memory, database connections, or LLM token budgets via traffic flood.
- **Mitigation:**
  - Redis token-bucket rate limiter: 60 req/min per IP/principal, tighter 10 req/min limit on generative tools.
  - Request body size capped at 64 KB; request timeout enforced at 8 seconds.
  - `LLMBudgetGuard` enforces a strict daily token and request quota, gracefully failing to cached responses when budget is exhausted.
  - AWS ALB drops invalid headers and shields private subnets.

### 2.6 Elevation of Privilege (Authorization)
- **Threat:** Non-privileged runtime app attempts to alter schema or access other tenants' data.
- **Mitigation:**
  - Strict database role separation: runtime `sahayak_app` role has DML privileges only (SELECT, INSERT, UPDATE, DELETE); DDL (CREATE, DROP, ALTER) is blocked and rejected by PostgreSQL.
  - Every repository query explicitly scopes rows by verified `user_id`. Automated cross-user isolation test suite (`tests/security/isolation.py`) runs in CI on every tool.
  - AWS IAM execution and task roles follow least privilege with zero wildcard IAM policies.
