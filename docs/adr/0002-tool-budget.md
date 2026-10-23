# 0002 — Tool budget for the initial add-on

Status: Accepted
Date: 2026-10-21

## Context

Amazon’s current MCP Toolkit documentation does not publish a numerical maximum for tool count or tool-description length. Alexa refreshes tools only when the add-on is deployed. An unnecessarily large or overlapping public tool surface remains a certification and UX risk.

## Options considered

1. Publish all useful capabilities as individual tools without a budget.
2. Keep a configurable, conservative budget until Amazon publishes a limit.

## Decision

Use the existing defaults of 15 total tools as an **ASSUMPTION**, enforced by test in T0.11.

**Decision Update (2026-10-23):** Based on verification finding V1 (`docs/alexa/findings.md` confirming Amazon publishes no numeric limit for tools per add-on) and PRD §10.1 option (b), raise `MAX_TOOLS_PER_MODULE` from 4 to 6. This cleanly accommodates the 6 Academics tools (`quiz_start`, `quiz_answer`, `flashcards`, `study_plan`, `progress_report`, `topic_brief`) as dedicated, voice-optimized tools without multiplexer complexity.

## Consequences

Academics can register its full suite of tools (`progress_report` in T3.13 and `topic_brief` in T3.14) within the 6-tool per-module ceiling and 15-tool global ceiling.
