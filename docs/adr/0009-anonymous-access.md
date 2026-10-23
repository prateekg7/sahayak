# 0009 — Anonymous and linked access

Status: Accepted
Date: 2026-10-21

## Context

Amazon documents account linking as optional and requires 401 or 403 only when a tool needs user identity. The product needs a useful unlinked path without exposing persistent user data.

## Decision

Allow anonymous use only for explicitly non-persistent tools and ephemeral quiz sessions. Require a linked account for saved progress, flashcards, study plans, and all future persistent features.

## Consequences

Every tool must declare its access policy. Anonymous calls have no user identity, and repositories must never accept a user ID from tool input.
