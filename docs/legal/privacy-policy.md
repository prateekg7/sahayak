# Privacy Policy for Sahayak

**Last Updated:** October 23, 2026
**Effective Date:** October 23, 2026

Sahayak ("we", "our", or "us") provides a modular voice assistant platform delivered as an Alexa+ Model Context Protocol (MCP) add-on. This Privacy Policy describes how we collect, use, store, export, and delete your information when you interact with the Sahayak voice assistant.

---

## 1. Scope and Voice Architecture
- **Voice Processing**: When you speak to an Alexa-enabled device, your audio is processed directly by Amazon Alexa. Sahayak does not receive, record, or store your voice audio. Amazon sends only the resolved text or structured tool arguments over a secure HTTPS connection to our MCP server.
- **Stateless MCP Interaction**: Sahayak operates as a stateless MCP server. We maintain no in-memory session states between separate conversational turns. State handles (such as quiz or flashcard identifiers) are passed within structured tool envelopes.

---

## 2. Information We Collect
We practice strict data minimization and collect only what is necessary to deliver the features you request:
1. **Identity & Authentication**: When you link your account, we receive a cryptographically signed OAuth2 JSON Web Token (JWT). We store your external identity provider subject identifier and issuer URL. We do not store your passwords.
2. **Localization & Preferences**: Your preferred locale (e.g., `en-US`, `en-IN`) and timezone to format dates and schedules accurately for speech.
3. **Application & Learning Records**:
   - Quizzes, questions answered, and scores.
   - Spaced-repetition flashcards and review intervals.
   - User-created study plans and tasks.
4. **Technical & Audit Logs**:
   - Cryptographically hashed client IP addresses (SHA-256) for abuse prevention. We never store raw IP addresses.
   - Structured audit logs of security actions (logins, exports, deletions) without sensitive payloads.

---

## 3. How We Use Your Information
- To deliver interactive quizzes, explanations, and study assistance.
- To schedule spaced-repetition reviews according to memory decay curves.
- To prevent abuse, rate limit malicious requests, and protect system integrity.
- We **never** sell your data, use your private notes for model training, or display third-party advertisements.

---

## 4. Third-Party Services and Grounding
- **Knowledge Grounding**: To ensure facts and quiz questions are grounded in authoritative material, public factual sources (e.g. Wikimedia Foundation REST API) may be queried using topic keywords. No personal data or user identifiers are ever transmitted to third-party knowledge sources.
- **AI Inference**: When language models are queried, user identifiers are stripped and queries are sandboxed.

---

## 5. Data Retention Policy
- **Audit Logs**: Retained for 90 days for compliance and fraud detection, then automatically pruned.
- **Idempotency Keys**: Stored with an automatic Time-To-Live (TTL) of 24 hours, then automatically purged.
- **User Records**: Maintained until you request erasure or unlink your account.

---

## 6. Your Rights: Export and Erasure (GDPR / CCPA / Certification)
You have complete control over your personal data:
- **Right to Access / Data Portability**: You may request an export of all data associated with your account at any time. Our platform compiles a structured JSON export encompassing your profile, identities, quiz history, flashcards, study plans, and audit trail.
- **Right to Erasure ("Right to be Forgotten")**: You may request permanent deletion of your account. Deletion cascades across all databases and schemas:
  - User profile and identities are deleted.
  - Ephemeral idempotency keys are removed.
  - Audit logs are permanently anonymized (user reference disassociated).
  - No rows referencing your user identifier remain.

---

## 7. Security Safeguards
- All data in transit is encrypted using TLS 1.3.
- Database records are encrypted at rest with AES-256.
- Strict cross-user isolation and tenant boundaries are enforced in code and database queries.
- Automated log redaction strips tokens, emails, and sensitive values before writing to log sinks.

---

## 8. Contact Us
For questions regarding this policy, or to submit a data export or deletion request, contact:
- **Email**: `support@sahayak.app` (or `privacy@sahayak.app`)
- **Developer**: Sahayak Team
