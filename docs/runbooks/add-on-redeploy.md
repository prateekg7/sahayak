# Operational Runbook: Alexa+ Add-on Redeployment

## When Required
Whenever a tool name, input argument schema, or description changes on the MCP server, an add-on redeployment is required so Amazon's Alexa+ router recognizes the new tool signature.

---

## Procedure
1. **Regenerate Tool Snapshot:**
   ```bash
   make snapshot
   ```
2. **Verify Tool Budget & Snapshot:**
   ```bash
   make snapshot-check
   ```
3. **Commit with Directive:**
   Mark commit message body with: `requires alexa-ai deploy`.
4. **Deploy Application Container:**
   Deploy the updated container image to Production first.
5. **Deploy Add-on Manifest to Alexa+:**
   Trigger GitHub Workflow `.github/workflows/alexa_deploy.yml` or run:
   ```bash
   alexa-ai deploy --manifest alexa/addon.json
   ```
6. **Verify in Simulator:**
   Execute `python scripts/alexa_simulator_runner.py --url https://api.sahayak.app`.
