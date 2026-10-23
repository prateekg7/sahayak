# Low-Cost Deployment Guide for Sahayak

This guide documents how to deploy **Sahayak** in production or staging environments for **under $10/month** (or within the free tier), as an alternative to AWS ECS Fargate + RDS + ElastiCache.

---

## 1. Architecture Overview

Sahayak is designed from the ground up to be **stateless and modular**:
- **Stateless HTTP Transport:** Accepts Streamable HTTP requests on `/mcp`.
- **Health Checks:** Exposes `/healthz` (liveness) and `/readyz` (readiness).
- **Persistence:** Any standard PostgreSQL 16+ database.
- **Cache & Queue:** Any Redis 7+ server (including serverless Redis).
- **Background Worker:** A lightweight asynchronous Python process (`python -m sahayak.worker`).

Because the MCP server holds no in-memory session state, it scales to zero on serverless container platforms without dropping Alexa+ user sessions.

---

## 2. Low-Cost Stack Options

| Component | Recommended Provider | Free Tier / Cost | Why It Fits |
|---|---|---|---|
| **MCP Server Container** | **Google Cloud Run** or **Fly.io** | 2M reqs/mo free (Cloud Run); 3 shared VMs free (Fly.io) | Native HTTP/2 & Streamable HTTP support, scales to 0, automated TLS |
| **Background Worker** | **Fly.io** or **Render** | 1 background worker on Fly free tier (~256MB RAM) | Dedicated async event outbox publisher and background job processor |
| **PostgreSQL Database** | **Neon** or **Supabase** | 0.5GB storage, autoscaling compute (Free) | PostgreSQL 16, pgvector, SSL enforced, automated point-in-time recovery |
| **Redis Cache & Limiter** | **Upstash Redis** | 10,000 commands/day free, then $0.20/100k commands | Zero-idle cost, TLS encryption, REST or standard redis protocol |
| **OAuth IdP** | **AWS Cognito** (50k MAUs free) or **Auth0** (7.5k MAUs free) | Free | Standard OAuth2 / PKCE support for Alexa+ account linking |
| **Domain & DNS** | **Cloudflare** | Free SSL, DDoS protection, edge CDN | Free TLS certificates and edge routing |

**Total Estimated Monthly Cost:** **$0.00 – $5.00 / month** for up to 100,000 monthly active voice turns.

---

## 3. Deploying to Google Cloud Run

### Step 3.1: Build and Push Docker Image
```bash
# Authenticate with Google Cloud
gcloud auth configure-docker

# Build container using project Dockerfile
docker build -t gcr.io/<PROJECT_ID>/sahayak:latest .
docker push gcr.io/<PROJECT_ID>/sahayak:latest
```

### Step 3.2: Configure Environment and Secrets
Store secrets in Google Secret Manager:
```bash
gcloud secrets create sahayak-db-password --data-file=- <<< "YourNeonDbPassword"
gcloud secrets create sahayak-gemini-key --data-file=- <<< "AIzaSy..."
gcloud secrets create sahayak-groq-key --data-file=- <<< "gsk_..."
```

### Step 3.3: Deploy Service
```bash
gcloud run deploy sahayak-api \
  --image gcr.io/<PROJECT_ID>/sahayak:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000 \
  --min-instances 0 \
  --max-instances 5 \
  --memory 512Mi \
  --cpu 1 \
  --set-env-vars ENVIRONMENT=prod,PORT=8000 \
  --set-env-vars DATABASE_URL="postgresql+asyncpg://sahayak_app:$(gcloud secrets versions access latest --secret=sahayak-db-password)@ep-cool-db.us-east-2.aws.neon.tech/sahayak?ssl=require" \
  --set-env-vars REDIS_URL="rediss://default:YourUpstashKey@us1-speedy-server.upstash.io:6379" \
  --set-secrets GEMINI_API_KEY=sahayak-gemini-key:latest \
  --set-secrets GROQ_API_KEY=sahayak-groq-key:latest
```

---

## 4. Deploying to Fly.io

Fly.io provides a great low-cost platform with built-in private networking.

### Step 4.1: `fly.toml` Configuration
Create `fly.toml` in repository root:
```toml
app = "sahayak-voice"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[env]
  ENVIRONMENT = "prod"
  PORT = "8000"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 1

  [http_service.concurrency]
    type = "requests"
    soft_limit = 250
    hard_limit = 500

[[http_service.checks]]
  interval = "15s"
  timeout = "2s"
  grace_period = "5s"
  method = "GET"
  path = "/healthz"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"
```

### Step 4.2: Deploying the Background Worker on Fly.io
Deploy a separate machine without public HTTP ports for `sahayak.worker`:
```bash
fly machine run . \
  --entrypoint "uv run python -m sahayak.worker" \
  --region iad \
  --vm-size shared-cpu-1x \
  --vm-memory 256mb \
  --restart always
```

---

## 5. Verification Checklist

Regardless of host, verify the following before connecting Alexa+:
1. **Liveness & Readiness:**
   ```bash
   curl -i https://<YOUR_DOMAIN>/healthz
   # Should return HTTP 200 {"status":"ok"}
   ```
2. **MCP SSE / Streamable HTTP Protocol Negotiation:**
   ```bash
   npx @modelcontextprotocol/inspector https://<YOUR_DOMAIN>/mcp
   ```
3. **Database Roles Check:**
   Confirm your database user has DML privileges on `core` and `academics` schemas, but **cannot** run DDL statements, using `python scripts/verify_app_db_role.py --db-url ...`.
