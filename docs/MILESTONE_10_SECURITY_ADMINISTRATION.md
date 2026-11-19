# Milestone 10 — Enterprise Security & Administration

## Implemented
- MFA/TOTP for organisation users with one-time recovery codes.
- Email verification tokens.
- Password reset tokens with expiry and single-use semantics.
- Login attempt tracking and temporary account lockout.
- Session clearing/rotation at authentication boundaries.
- Security headers including CSP, frame protection, MIME sniffing protection and HSTS when HTTPS is detected.
- Request rate limiting foundation.
- Permission registry and role-permission enforcement helpers.
- Platform administration remains isolated from tenant accounts.

## Setup
Run database migration generation and review the resulting SQL before production: `flask --app run.py db migrate -m "milestone 10 security and administration"` then `flask --app run.py db upgrade`.
Seed tenant permissions with `flask --app run.py seed-permissions`.

## Email
Configure SMTP and `PUBLIC_BASE_URL` to enable email verification and password reset delivery. Without SMTP, the application intentionally does not claim that email delivery is operational.

## MFA
Users can enable MFA at `/auth/mfa/setup`. MFA uses TOTP and hashed recovery codes.

## Production requirements
Use Redis-backed rate limiting rather than `memory://` for multi-instance production. Configure HTTPS, SMTP, a strong `SECRET_KEY`, PostgreSQL, and backup/restore procedures.
