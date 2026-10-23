# 0015 — Government Scheme Finder Rules Engine & Curated Dataset

Status: Accepted
Date: 2026-10-24

## Context

Phase 12 Task 4 (`scheme_finder` tool) provides voice-guided access to Indian national and state welfare schemes (e.g., PM-Kisan, Ayushman Bharat, PM Awas Yojana, Sukanya Samriddhi Yojana, Atal Pension Yojana, PM Mudra Yojana).

Key requirements and constraints:
1. **Deterministic Accuracy**: Welfare eligibility rules involve legal thresholds (age brackets, income ceilings, landholding criteria, occupation limits). Delegating eligibility computation to an LLM risks hallucinating qualifications or giving false assurances to citizens in need.
2. **Curated Versioned Dataset**: Government scheme parameters evolve with annual union and state budgets. All scheme metadata must be versioned in-tree (JSON/YAML) with mandatory official portal links, verified benefit summaries, and validation scripts enforced in CI.
3. **Voice UX (One Fact at a Time)**: Per voice UX standards (PRD §9.3 & §10), when a user's eligibility cannot be determined due to missing parameters, the tool must ask for **exactly one missing fact** rather than asking for five fields simultaneously.
4. **Statutory Guidance Disclaimer**: Voice answers must clearly disclaim: "This is guidance, not an official decision. Check the official portal to apply."
5. **Access Policy**: Read-only civic information allows anonymous access (`@allow_anonymous`) per ADR 0009.

## Options Considered

1. **Scraping External Welfare Portals dynamically**:
   - *Pros*: Reflects online portal redesigns.
   - *Cons*: Scraping government portals is fragile, violates terms of service, and incurs multi-second latency violating voice budgets.
2. **LLM Prompt-Based Eligibility Decision**:
   - *Pros*: Flexible natural language parsing.
   - *Cons*: Non-deterministic, prone to policy hallucinations, unverifiable in safety audits.
3. **Curated Versioned Dataset with Pure Code Declarative Rules Engine**:
   - *Pros*: 100% deterministic, instant execution (<10 ms), validated in CI with link verification, supports step-by-step missing fact clarification, and produces clear spoken reasons for qualification or disqualification.
   - *Cons*: Requires periodic manual or scheduled curation upon government budget updates.

## Decision

We adopt Option 3:
- **Dataset**: `src/sahayak/modules/local_info/data/schemes.json` containing 20+ prominent national welfare schemes with official portal links, target beneficiaries, benefit summaries, and structured criteria.
- **Rules Engine**: `DeclarativeSchemeEngine` implementing pure code rule matching across `age`, `annual_income_inr`, `occupation`, `state`, `gender`, and `landholding`.
- **Clarification Loop**: If vital criteria are missing, the engine identifies the single highest-entropy missing fact and asks for it directly in speech.
- **Mandatory Disclaimer**: Automatically embedded in all spoken summaries and response metadata.
- **CI Gate**: `scripts/validate_schemes.py` running in test/lint gates to fail if any scheme lacks verified source links or last verified dates.
- **Tool Surface**: `scheme_finder` tool supporting `find`, `explain`, and `check_eligibility` actions with `@allow_anonymous`.

## Consequences

- Citizens receive verified, deterministic welfare eligibility advice in seconds.
- Voice interactions feel conversational and respect the "one missing fact at a time" rule.
- Official portal URLs empower users to take direct application steps.
