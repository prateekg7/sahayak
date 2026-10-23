# Alexa+ MCP verification findings

Checked: 2026-10-21

These are local engineering records. They are intentionally ignored by Git; only `README.md` is tracked as Markdown.

| ID | Finding | Source and conclusion | Status |
|---|---|---|---|
| V1 | Tool count and tool-description limit | Amazon's MCP Toolkit documentation publishes no numeric maximum. Keep the product default of 15 tools total and 4 per module as an **ASSUMPTION**; enforce it in configurable tests and revisit before launch. | Docs silent |
| V2 | Timeout and response size | The QuickStart requires a round-trip query response latency below 500 ms. It publishes no maximum response byte size. The former 8-second timeout assumption is invalid as a latency target; retain only a configurable transport timeout until implementation verifies SDK behavior. | Verified / docs silent on size |
| V3 | Account linking | MCP add-ons use OAuth 2.1 authorization-code flow with PKCE S256 and refresh tokens. The PRM document is at `/.well-known/oauth-protected-resource`; the canonical MCP URI is the `resource`; static client registration is required; every Alexa redirect URI must be registered. Alexa sends bearer tokens in `Authorization`; it does not support `WWW-Authenticate` in the unauthenticated 401 response. | Verified |
| V4 | Supported locales | The MCP Toolkit QuickStart documents `en-US` and does not publish a general MCP locale matrix. The broader Alexa interfaces table is not evidence for MCP Toolkit locale support. Launch with `en-US` only as an **ASSUMPTION**. | Docs silent |
| V5 | Certification | Certification requires the add-on to meet published functional and policy requirements. Listing metadata includes HTTPS privacy-policy and terms URLs, required media assets, and 3–4 example phrases. The certification page says final criteria will be provided before general availability; do not treat the preliminary list as complete. | Verified / evolving |
| V6 | Elicitation | Alexa+ uses the MCP elicitation framework to gather missing context, but Amazon does not publish an MCP Toolkit API contract sufficient to rely on it for v1 flows. Keep the product’s no-dependency stance. | Partially verified |
| V7 | Tool discovery caching | After tool or resource changes, `alexa-ai deploy` is required before the updates are available to customers. | Verified |
| V8 | Anonymous use | Account linking is optional, and Amazon gives general-information tools as an example that do not need it. Tools requiring identity must return 401 or 403, which starts linking. The product may offer explicitly non-persistent anonymous tools. | Verified |
| V9 | Request headers | The authenticated request uses a bearer token in the `Authorization` header and must not put it in a query string. Amazon does not document a specific `Origin` header value for MCP Toolkit calls; preserve configurable validation only when it is present. | Partially verified |
| V10 | Timers and proactive notifications | Alexa+ MCP add-on protocol does not support unsolicited background push notifications or device alarms to alert when a timer expires. Focus sessions store planned end timestamps and compute remaining/elapsed time on-demand when queried by voice. | Verified (docs silent on add-on push) |

## Sources

- https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart (checked 2026-10-21)
- https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-account-linking (checked 2026-10-21)
- https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-client-lifecycle (checked 2026-10-21)
- https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-certify (checked 2026-10-21)
- https://developer.amazon.com/docs/alexaplus/add-ons/policy-requirements (checked 2026-10-21)
