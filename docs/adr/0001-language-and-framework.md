# 0001 — Language and framework

Status: Accepted
Date: 2026-10-21

## Context

The PRD specifies a modular, stateless MCP server. It names Python 3.12, the official MCP Python SDK, FastAPI, Pydantic v2, and `uv` as the intended stack. A single language and packaging workflow are needed before application code is added.

## Options considered

1. Python 3.12 with FastAPI, the official MCP SDK, Pydantic v2, and `uv`.
2. TypeScript with an equivalent MCP stack.

## Decision

Use Python 3.12 with `uv` for reproducible environments. Add FastAPI, the MCP SDK, and Pydantic only in the tasks that begin using them, so each dependency is introduced with its purpose and tests. This initial commit establishes the package and quality-tool configuration.

## Consequences

The project requires a Python 3.12 interpreter even when a newer host Python exists. T0.2 adds typed configuration and its Pydantic dependency; T0.5 and T0.10 add the web and MCP dependencies after their pinned APIs have been verified.
