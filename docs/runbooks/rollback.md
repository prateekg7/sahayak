# Operational Runbook: Rollback Procedures

## Objective
Quickly revert a failed deployment to the previous stable state without data loss.

---

## Fast Automated Rollback
If a deployment fails the post-deploy smoke test window, CI executes:
```bash
python scripts/rollback.py --cluster sahayak-prod-cluster --service sahayak-prod-app
```

## Manual Emergency Rollback
1. Open the AWS ECS Console or run AWS CLI:
   ```bash
   # Identify prior active revision (e.g., from :14 to :13)
   aws ecs update-service \
     --cluster sahayak-prod-cluster \
     --service sahayak-prod-app \
     --task-definition sahayak-prod-app:13 \
     --force-new-deployment
   ```
2. Verify ECS service stability:
   ```bash
   python scripts/smoke_test.py --url https://api.sahayak.app --iterations 5
   ```
3. Database Considerations:
   Because all migrations follow the **expand/contract** pattern, rolling back container code does not require rolling back the database schema.
