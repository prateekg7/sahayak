# 0003 — MCP account-linking contract

Status: Accepted
Date: 2026-10-21

## Context

Amazon’s MCP account-linking guide specifies OAuth 2.1 authorization code with PKCE S256, refresh tokens, protected-resource metadata, static client registration, and bearer-token authentication. It explicitly marks `WWW-Authenticate` in a 401 response as unsupported for this integration.

## Options considered

1. Implement the documented OAuth 2.1 resource-server contract and keep the authorization-server provider configurable.
2. Choose an identity provider now and couple core authentication to it.

## Decision

Implement the documented resource-server contract. Serve PRM at `/.well-known/oauth-protected-resource`; validate bearer tokens from the `Authorization` header; use 401 or 403 without `WWW-Authenticate` to trigger linking. Defer selection of Cognito versus Auth0 until the owner supplies the cloud and identity-provider decision.

## Consequences

T1.3 must not emit `WWW-Authenticate`. T1.7 requires the owner’s IdP account, public HTTPS endpoint, client settings, and every Alexa redirect URI displayed by the CLI or Developer Hub.
