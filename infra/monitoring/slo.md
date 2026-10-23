# Sahayak Service Level Objectives (SLOs) & Alert Routing

This document defines the production Service Level Indicators (SLIs), Service Level Objectives (SLOs), error budgets, and operational alert routing rules for Sahayak per PRD §10 and tasks.md T4.4.

---

## 1. Availability SLO: 99.9%

### SLI Definition
The proportion of valid HTTP MCP tool invocations that return a successful result (`ok: true` or valid business error without 5xx status codes) over a rolling 30-day window:

$$\text{Availability} = \frac{\sum \text{Tool Calls with } \text{status} \neq 5xx}{\sum \text{Total Tool Calls}} \times 100\%$$

- **Target:** **$\ge 99.9\%$**
- **Monthly Error Budget:** 0.1% of requests (equivalent to ~43.2 minutes of total downtime per month).

---

## 2. Latency SLOs (Voice Turn-by-Turn Experience)

In voice interaction, high latency degrades user conversation flow. Per PRD §1.5:

| Interaction Type | SLI (p95 Target) | Rationale |
|---|---|---|
| **Deterministic Tool Invocations** (`quiz_answer`, `flashcards.grade`, `progress_report`) | **$\le 800\text{ ms}$** | Code calculations and DB queries must respond instantly |
| **Grounded LLM Generations** (`quiz_start` cache-miss, `topic_brief`) | **$\le 3500\text{ ms}$** | Streamable synthesis with Wikipedia retrieval |
| **Health Checks** (`/healthz`, `/readyz`) | **$\le 100\text{ ms}$** | ALB and container health probes |

---

## 3. Operational Alerts & Escalation Matrix

| Alarm Name | Threshold | Evaluation Window | Severity | Action / Destination |
|---|---|---|---|---|
| `high-error-rate` | 5XX rate > 1.0% | 5 minutes | **P1 (Critical)** | PagerDuty / On-call engineer; triggers auto-rollback if post-deploy |
| `high-latency-p95` | ALB p95 > 800ms | 10 minutes (2 periods) | **P2 (Major)** | Slack `#ops-alerts` & On-call |
| `rds-high-connections` | Connections > 80% max | 10 minutes | **P2 (Major)** | Slack `#ops-alerts`; scale connection pool or review query leaks |
| `redis-high-memory` | Memory > 80% | 10 minutes | **P2 (Major)** | Check LRU eviction rate and key TTL settings |
| `llm-fallback-spike` | Fallbacks > 5/min | 1 minute | **P3 (Warning)** | Check primary LLM provider status page (Gemini / Groq) |
| `llm-budget-exhaustion` | Any exhaustion count > 0 | 5 minutes | **P2 (Major)** | Alert team; fallback to cached questions / concise prompts |
| `acm-cert-expiry` | Days to expiry < 30 | 1 day | **P3 (Warning)** | Renew DNS validation records for ACM certificate |
