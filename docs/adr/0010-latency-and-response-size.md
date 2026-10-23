# 0010 — Alexa+ latency and response-size limits

Status: Accepted
Date: 2026-10-21

## Context

The MCP Toolkit QuickStart requires the MCP server to meet a round-trip query response latency below 500 ms. Amazon does not publish a response-byte maximum. The PRD’s prior default 8-second timeout and five-second synchronous generation target conflict with this requirement.

## Decision

Treat sub-500 ms round-trip latency as the launch constraint. T0.10 must use a configurable transport deadline that remains below this budget after framework overhead. Content generation must be pre-generated or otherwise make fast cache-backed responses possible; synchronous multi-second LLM generation cannot be a launch dependency. Keep the 8 KiB response cap as a configurable conservative **ASSUMPTION** until Amazon publishes a limit.

## Consequences

The PRD and future quiz-generation tasks need a latency-design revision before implementation. T0.10 and T3.3 must test the resulting deadline and cache-miss behavior against the verified constraint.
