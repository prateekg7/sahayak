# Operational Runbook: Database Backup & Point-in-Time Recovery

## Objectives
- **Recovery Point Objective (RPO):** $\le 5\text{ minutes}$.
- **Recovery Time Objective (RTO):** $\le 30\text{ minutes}$.

---

## Automated Backups & PITR
- AWS RDS automated backups run daily between 03:00 - 04:00 UTC with 30-day retention in production.
- Continuous WAL archiving provides Point-in-Time Recovery (PITR) to any second within the retention window.

---

## Recovery Procedure
1. **Restore DB Instance to Point-in-Time:**
   ```bash
   aws rds restore-db-instance-to-point-in-time \
     --source-db-instance-identifier sahayak-prod-postgres \
     --target-db-instance-identifier sahayak-prod-postgres-restored \
     --restore-time "2026-10-23T12:00:00Z" \
     --db-subnet-group-name sahayak-prod-db-subnet-group \
     --vpc-security-group-ids "sg-xxxxxx"
   ```
2. **Verify Database Integrity:**
   Run verification script:
   ```bash
   python scripts/db_restore_drill.py --verify-target --db-url "postgresql+asyncpg://..."
   ```
3. **Switch Endpoint:**
   Update Route 53 private hosted zone or Secrets Manager `DATABASE_URL` to point to the restored DB instance.
