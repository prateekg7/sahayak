# Operational Runbook: Privacy & GDPR User Data Requests

## Objective
Execute GDPR / CCPA Right to Access (Export) and Right to be Forgotten (Deletion) requests using built-in privacy tooling.

---

## 1. Export User Data
When a user requests an export of all their personal data:
```bash
PYTHONPATH=src uv run python -m sahayak.core.privacy export --user-id "<USER_UUID>" --output-file "export-<USER_UUID>.json"
```
The resulting JSON bundle includes:
- Account identities (`core.user_identities`)
- Quizzes and answer history (`academics.quizzes`, `academics.quiz_questions`)
- Decks and flashcards (`academics.decks`, `academics.cards`)
- Study plans and scheduled tasks (`academics.study_plans`, `academics.plan_tasks`)
- Topic statistics (`academics.topic_stats`)
- Activity log entries (`academics.activity_log`)

---

## 2. Delete User Data (Right to be Forgotten)
When a user requests complete deletion:
```bash
PYTHONPATH=src uv run python -m sahayak.core.privacy delete --user-id "<USER_UUID>"
```
- Performs cascading transactional deletion across all application schemas.
- Records an audit log entry in `core.audit_log` (`action: user_deleted`, IP anonymized, zero PII preserved).
- Returns confirmation payload verifying 0 records remain for `<USER_UUID>`.
