# External integration architecture (Milestone 6)

This release adds the tenant-scoped connection record and a separate Fernet credential-envelope helper. It does **not** complete provider authentication or synchronisation.

## Google Drive — planned adapter

1. Register a Google OAuth application and verify the product's consent screen.
2. Use an authorization-code flow with `state` bound to the authenticated tenant and user, PKCE where supported, exact redirect URI matching, and one-time state validation.
3. Request the narrowest Drive read-only scopes possible. Do not request broad write access for document retrieval.
4. Exchange the code server-side. Encrypt refresh/access tokens with `INTEGRATION_ENCRYPTION_KEY`; never put tokens in browser storage, logs, task arguments, or audit details.
5. Store the provider account identifier, approved scopes and token expiry as non-secret metadata. Refresh tokens server-side and rotate/revoke on disconnect.
6. Import only folders explicitly selected by a tenant administrator. Re-check the tenant and folder grant on every sync and every file retrieval.
7. Record sync cursor, source file ID, content hash and audit events. Treat imported document text as untrusted reference data, not executable instructions.

## Email — planned adapter

- Support Gmail API and Microsoft Graph through separate provider adapters.
- Begin with read-only access only if the business explicitly enables it. Sending mail requires a separate capability, an exact message preview, and a human approval tied to the exact recipient, subject and body hash.
- Never let an AI employee send, forward, delete or modify messages simply because a prompt requests it. Re-check the approval and current employee permission immediately before any future send operation.
- Store provider tokens only in the encrypted credential envelope. Apply mailbox/folder allowlists, rate limits, audit logging, revocation and token expiry handling.

## General external API rules

- Provider adapters must be allowlisted in server code. Do not accept arbitrary user-supplied base URLs; this prevents turning integrations into an SSRF proxy.
- Use outbound network restrictions, TLS certificate verification, strict timeouts, response-size limits and JSON schema validation.
- Keep secrets out of prompts, AI context, logs, error messages, URLs and Celery task payloads.
- Separate read capabilities from write capabilities. Require human approval for external commitments and high-impact actions.
- Bind approvals to a canonical action payload hash and expiry. Revalidate tenant, user, employee capability, approval status and payload hash at execution time.
- Add provider-specific threat modelling, security review and integration tests before enabling any live connector.

## Current implementation boundary

`IntegrationConnection` is tenant-scoped and stores only an encrypted credential envelope. `app/integrations/vault.py` provides encryption/decryption helpers using a dedicated key. No OAuth routes, provider API clients, email send actions, or Drive sync jobs are enabled in this milestone. The UI intentionally shows these connections as not connected until those provider flows are implemented and reviewed.
