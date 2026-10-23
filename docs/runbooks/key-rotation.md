# Operational Runbook: Credential & API Key Rotation

## Overview
Procedures for zero-downtime rotation of API keys, database credentials, and JWT signing keys.

---

## 1. Rotating LLM Provider Keys (Gemini / Groq)
1. Generate new API key in Google AI Studio or Groq Console.
2. Update AWS Secrets Manager secret:
   ```bash
   aws secretsmanager update-secret \
     --secret-id sahayak-prod-app-secrets \
     --secret-string '{"GEMINI_API_KEY":"new_key_here", ...}'
   ```
3. Trigger rolling restart of ECS services:
   ```bash
   aws ecs update-service --cluster sahayak-prod-cluster --service sahayak-prod-app --force-new-deployment
   aws ecs update-service --cluster sahayak-prod-cluster --service sahayak-prod-worker --force-new-deployment
   ```
4. Revoke old key after new tasks are confirmed healthy in `/healthz`.

---

## 2. Rotating Database Passwords
1. Add new secondary password in PostgreSQL:
   ```sql
   ALTER ROLE sahayak_app WITH PASSWORD 'new_password';
   ```
2. Update `DATABASE_PASSWORD` in AWS Secrets Manager.
3. Trigger rolling restart of ECS tasks.
4. Verify application connects with new password via `scripts/verify_app_db_role.py`.

---

## 3. Rotating OIDC / JWT Signing Keys
- AWS Cognito handles RS256 key rotation automatically by publishing new public keys to the JWKS endpoint `/.well-known/jwks.json`.
- Sahayak's JWKS cache refreshes public keys upon encountering an unknown `kid`, ensuring zero-downtime key rotation.
