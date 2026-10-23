# Operational Runbook: External LLM & Provider Outage

## Symptoms
- CloudWatch Alarm `llm-fallback-spike` triggers.
- Logs show repeated timeout or 503 errors from Gemini or Groq endpoints.

## Automatic System Behavior
1. **Circuit Breaker:** The LLM client automatically opens the circuit after 3 consecutive failures within 60 seconds.
2. **Provider Fallback:** Invocations immediately shift from Primary (`gemini-2.5-flash`) to Fallback (`groq-llama-3.3-70b-versatile`).
3. **Cache Fallback:** If both providers fail, quiz questions are served strictly from the pre-verified questions cache in PostgreSQL. `topic_brief` returns the sanitized Wikipedia extract directly.

## Manual Mitigation Steps
1. Verify status pages:
   - Google AI Studio Status: `https://status.cloud.google.com/`
   - Groq Cloud Status: `https://status.groq.com/`
2. If primary provider has prolonged outage, swap primary provider via AWS Secrets Manager:
   ```bash
   aws secretsmanager update-secret \
     --secret-id sahayak-prod-app-secrets \
     --secret-string '{"LLM_PRIMARY_PROVIDER":"groq", ...}'
   ```
3. Restart ECS tasks to pick up configuration immediately:
   ```bash
   aws ecs update-service --cluster sahayak-prod-cluster --service sahayak-prod-app --force-new-deployment
   ```
