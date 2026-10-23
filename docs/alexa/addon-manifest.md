# Alexa+ Add-on Registration & Listing Guide

This document records the configuration, metadata, and deployment process for the Sahayak MCP Add-on on Alexa+ per PRD §19.

---

## 1. Add-on Metadata

- **Add-on Name:** Sahayak
- **Add-on ID:** `amzn1.alexa-addon.sahayak-study-v1`
- **Initial Version:** `1.0.0`
- **Supported Locales:** `en-US`, `en-IN`
- **Transport:** Streamable HTTP over TLS
- **MCP Server URI:** `https://api.sahayak.app/mcp`
- **MCP Protocol Version:** `2025-11-25`

---

## 2. Example Phrases

The following example phrases route directly to Sahayak MCP tools:
1. *"Quiz me on photosynthesis."* $\rightarrow$ `quiz_start(topic="photosynthesis")`
2. *"Review my flashcards."* $\rightarrow$ `flashcards(action="review_next")`
3. *"Make a study plan for my chemistry exam on the 15th."* $\rightarrow$ `study_plan(action="create", ...)`
4. *"How am I doing in my quizzes?"* $\rightarrow$ `progress_report(scope="summary")`
5. *"Give me a quick brief on the French Revolution."* $\rightarrow$ `topic_brief(topic="French Revolution")`
6. *"Quiz me on my weak topics."* $\rightarrow$ `quiz_start(source="weak_topics")`

---

## 3. Account Linking Specification

- **Auth Grant Type:** Authorization Code Grant (OAuth 2.1 with PKCE)
- **Identity Provider:** AWS Cognito User Pool (`sahayak-prod-user-pool`)
- **Authorization URL:** `https://sahayak-auth.auth.us-east-1.amazoncognito.com/oauth2/authorize`
- **Token URL:** `https://sahayak-auth.auth.us-east-1.amazoncognito.com/oauth2/token`
- **Scopes Requested:**
  - `openid`: OIDC identity token
  - `email`: User email verification
  - `profile`: User display name / profile
  - `sahayak-api/academics.read`: Read access for flashcards, study plans, and reports
  - `sahayak-api/academics.write`: Write access to grade flashcards and submit quiz answers

---

## 4. Deployment Instructions

### Prerequisites
1. Installed Alexa AI CLI: `npm install -g @alexa/ai-cli`
2. Authenticate: `alexa-ai configure`

### Deployment
To register or update the add-on manifest with Amazon Alexa+:
```bash
# Verify tool snapshot matches production
make snapshot-check

# Deploy add-on manifest
alexa-ai deploy --manifest alexa/addon.json
```
Once deployed, verify tool discovery in the Local Inspector and run the test plan in the Web Simulator.
