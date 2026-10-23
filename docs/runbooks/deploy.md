# Operational Runbook: Application Deployment

## Objective
Safely deploy application containers and database migrations to Staging and Production with zero downtime and automatic health verification.

---

## Deployment Steps

1. **Trigger Automated Release Pipeline:**
   Pushing to `main` triggers `.github/workflows/release.yml`.
2. **Expand-Only Migrations:**
   The pipeline executes `alembic upgrade heads` using the `sahayak_migrator` role.
   *Rule:* Migrations must be purely additive (expand). Do not drop columns until the old application version is decommissioned.
3. **Staging Canary & Contract Suite:**
   Staging containers are updated via rolling deployment (minimum healthy percent = 100%).
   Automated contract suite replaying voice dialogues executes against staging URL.
4. **Production Deployment Approval:**
   Requires sign-off in GitHub Environments by a designated release engineer.
5. **Production Smoke Test Window:**
   `scripts/smoke_test.py --url https://api.sahayak.app --iterations 10` runs immediately post-deploy.
   If any health or latency check fails, automated rollback triggers automatically.
