# Alexa+ Add-on Certification Checklist & Readiness Verification

This document tracks readiness against Amazon's official **Alexa+ Add-on Certification Guidelines** per PRD §19 and tasks.md T4.9.

---

## 1. Metadata & Listing Quality Checklist
- [x] **Add-on Name:** "Sahayak" is distinctive, easy to pronounce by voice, and does not infringe third-party trademarks.
- [x] **Short Description:** Under 160 characters ("Quiz yourself on any topic, review flashcards, and plan your study time.").
- [x] **Full Description:** Accurately details voice functionality, supported topics, spaced repetition algorithm, and planner features without hype.
- [x] **Example Phrases:** All 6 listed example phrases route directly to active MCP tools in automated contract tests.
- [x] **Category:** Education & Reference.

---

## 2. Policy & Compliance Checklist
- [x] **Privacy Policy URL:** Published at `https://sahayak.app/privacy` (matches `docs/legal/privacy-policy.md`).
- [x] **Terms of Service URL:** Published at `https://sahayak.app/terms` (matches `docs/legal/terms.md`).
- [x] **Support Contact:** `support@sahayak.app` configured with monitored inbox.
- [x] **No Unexpected Purchasing:** `allowsPurchases` set to `false`.
- [x] **No Unsolicited Advertising:** `containsAds` set to `false`.
- [x] **Child Safety (COPPA):** Service is intended for general audiences; no personal data collected from children under 13 without consent.

---

## 3. Voice UX & Dialogue Standards
- [x] **Speech Length Limits:** All `spoken_summary` responses verified $\le 300$ characters.
- [x] **No Raw Formatting in Speech:** Verified that markdown (`**`, `##`), URLs (`http://`, `https://`), and raw JSON are completely stripped from spoken outputs.
- [x] **One Step at a Time:** Conversation flows ask for only one missing parameter at a time.
- [x] **Correct Answer Concealment:** In quiz question turns, correct answers are withheld until after the user submits their answer.
- [x] **Actionable Voice Errors:** Errors explain what happened in plain English and provide a clear next step (e.g. *"This quiz has expired. Would you like to start a new quiz on photosynthesis?"*).

---

## 4. Security & Account Linking Compliance
- [x] **Transport Security:** Strict TLS 1.3 encryption on ALB endpoint with valid ACM certificate.
- [x] **OAuth 2.1 PKCE:** Authorization Code grant with PKCE flow.
- [x] **Scope Minimization:** Requested scopes (`academics.read`, `academics.write`) strictly match functional requirements.
- [x] **RFC 9728 Compliance:** Unauthenticated requests return `401` or `403` with protected-resource metadata without standard `WWW-Authenticate` header to trigger Alexa+ native account-linking cards.
- [x] **Right to be Forgotten:** Full GDPR user export and cascading purge verified by automated integration test.

---

## 5. Certification Submission Record
- **Add-on ID:** `amzn1.alexa-addon.sahayak-study-v1`
- **Submitted Version:** `1.0.0`
- **Target Locales:** `en-US`, `en-IN`
- **MCP Endpoint:** `https://api.sahayak.app/mcp`
- **Status:** Pre-submission verification complete; all automated criteria passed.
