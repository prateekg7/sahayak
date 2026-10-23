# Alexa+ Account Linking Configuration Guide (ADR 0003 / T1.7)

This document provides exact values and step-by-step instructions for configuring OAuth 2.1 Account Linking between Amazon Alexa+ and the Sahayak MCP server.

---

## 1. OAuth 2.1 Architecture
Per **ADR 0003** and the Amazon MCP Toolkit specification:
- **Flow**: Authorization Code Grant with **PKCE (S256)** and refresh tokens.
- **Client Type**: Confidential client with client secret (or public client with PKCE).
- **PRM Endpoint**: Hosted at `https://<api-domain>/.well-known/oauth-protected-resource` (RFC 9728).
- **401 Response Behavior**: When an unlinked user invokes a protected tool, Sahayak returns HTTP 401 **without a `WWW-Authenticate` header**, instructing Alexa to trigger the account-linking card/prompt.

---

## 2. Infrastructure as Code (AWS Cognito)
The complete Terraform definition is located in `infra/terraform/idp/`:
- `aws_cognito_user_pool`: Manages user credentials, password policies, and email verification.
- `aws_cognito_resource_server`: Registers the `sahayak-api` audience identifier with custom scopes:
  - `sahayak-api/academics.read`
  - `sahayak-api/academics.write`
- `aws_cognito_user_pool_client`: Configured with authorization code grant, PKCE, secret, and Alexa callback URLs.

### Deploying the IdP
```bash
cd infra/terraform/idp
terraform init
terraform apply -var="environment=staging" -var="cognito_domain_prefix=sahayak-auth-staging"
```

---

## 3. Values for Amazon Alexa Add-on Console
When configuring your add-on in the **Amazon Developer Console** or Alexa AI CLI:

| Setting | Value | Notes |
|---|---|---|
| **Security Scheme** | `OAuth 2.0` / `OAuth 2.1` | Authorization Code Grant with PKCE |
| **Authorization URI** | `https://<domain_prefix>.auth.<region>.amazoncognito.com/oauth2/authorize` | From Terraform output `authorization_endpoint` |
| **Access Token URI** | `https://<domain_prefix>.auth.<region>.amazoncognito.com/oauth2/token` | From Terraform output `token_endpoint` |
| **Client ID** | `<user_pool_client_id>` | From Terraform output `user_pool_client_id` |
| **Client Secret** | `<user_pool_client_secret>` | From Terraform output `user_pool_client_secret` |
| **Client Authentication** | `HTTP Basic (Credentials in Authorization Header)` | Standard OAuth2 Basic Auth |
| **Scopes** | `openid email sahayak-api/academics.read sahayak-api/academics.write` | Space-delimited |

### Registered Redirect URLs in IdP:
- `https://pitangui.amazon.com/api/flutter/skill-linking/callback` (North America)
- `https://layla.amazon.com/api/flutter/skill-linking/callback` (EU)
- `https://alexa.amazon.co.jp/api/flutter/skill-linking/callback` (Far East)
- `https://oauth.developer.amazon.com/response_types/token/cb` (Developer Portal)

---

## 4. Sahayak Server Configuration (`.env`)
Provide the following values in your `.env` file on the Sahayak server:
```dotenv
OIDC_ISSUER=https://cognito-idp.<aws-region>.amazonaws.com/<user-pool-id>
OIDC_AUDIENCE=sahayak-api
OIDC_JWKS_URL=https://cognito-idp.<aws-region>.amazonaws.com/<user-pool-id>/.well-known/jwks.json
```

---

## 5. Test User Creation & Manual Verification Flow

### Step 1: Create a test user in Cognito
```bash
aws cognito-idp admin-create-user \
  --user-pool-id <user-pool-id> \
  --username testuser@example.com \
  --user-attributes Name=email,Value=testuser@example.com Name=email_verified,Value=true \
  --temporary-password "TempPassword123!"

aws cognito-idp admin-set-user-password \
  --user-pool-id <user-pool-id> \
  --username testuser@example.com \
  --password "PermanentPassword123!" \
  --permanent
```

### Step 2: Generate PKCE Code Verifier & Challenge
```bash
# Generate 43-character random string (code_verifier)
CODE_VERIFIER="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
# Compute SHA256 base64url of code_verifier (code_challenge)
CODE_CHALLENGE="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
```

### Step 3: Authorize via Browser / Curl
Direct user to:
```
https://<domain_prefix>.auth.<region>.amazoncognito.com/oauth2/authorize?response_type=code&client_id=<client-id>&redirect_uri=https://oauth.developer.amazon.com/response_types/token/cb&scope=openid+email+sahayak-api/academics.read&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256
```
After login, extract `code` from the redirect callback query parameters.

### Step 4: Exchange Code for Access Token
```bash
curl -X POST "https://<domain_prefix>.auth.<region>.amazoncognito.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "<client-id>:<client-secret>" \
  -d "grant_type=authorization_code&client_id=<client-id>&code=<AUTH_CODE>&redirect_uri=https://oauth.developer.amazon.com/response_types/token/cb&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
```

### Step 5: Verify Token Against Sahayak MCP
```bash
curl -X POST "http://localhost:8000/mcp" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "protected_reader", "arguments": {"record_id": "test"}}}'
```
Response will return `"ok": true` with data.
