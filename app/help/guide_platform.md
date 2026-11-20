# AI Workforce — help guide for the platform owner

Page references are written like [[page:admin]]. The platform owner manages every business from the SaaS Administration Centre. Business workspaces have their own separate sign-in (/auth/login); the admin account does not work there, and a business account does not work on /platform/login.

## Signing in
1. Open /platform/login and enter the admin email and password.
2. Enter the 6-digit code from the authenticator app and tap **Continue**.
3. Five wrong passwords or five wrong codes lock the admin account for 15 minutes. A saved recovery code works in place of the 6-digit code; each works once.
- Turn on two-step codes for an admin with the server command `flask --app run.py enable-platform-admin-mfa` (Render → the web service → Shell). It prints a Secret to type into the authenticator app ("Enter a setup key" — only the letters and numbers, no `&`) and 8 recovery codes.
- Create an admin with `flask --app run.py create-platform-admin` in the same Shell.

## The SaaS Administration Centre ([[page:admin]])
| Section | Shows | You can |
| --- | --- | --- |
| Counters | Businesses, plans, subscriptions, payments | Read |
| Subscription plans | Monthly price, AI employee limit, task limit | Change the price, then **Update** |
| Businesses & subscriptions | Business, plan, status, period end | Change status, then save |
| Recent payments | Last 30 payments | Read |
| Security monitoring | Last 50 sign-ins, code checks and admin changes | Read |

## Plans and prices
- Prices are in GHS per month. Current: Starter GHS 450, Growth GHS 2,200, Business GHS 8,500.
- Limits are fixed in the code and reset if edited: Starter 3 AI employees / 100 tasks, Growth 10 / 500, Business 30 / 2,000. Only price edits last.
- Plans appear only after the first business signs up. Initial prices come from the Render settings PLAN_STARTER_AMOUNT, PLAN_GROWTH_AMOUNT, PLAN_BUSINESS_AMOUNT; after that, change them on the admin page.
- Prices were set to cover the AI cost even at full use: the app uses OpenAI GPT-5.5; a typical team job costs about USD 0.16 and at most about USD 0.36. Switching the Render setting OPENAI_MODEL to a cheaper model roughly halves AI cost.

## Subscription statuses
- **trialing** — free 14-day trial from sign-up
- **active** — paid and running (also use this to give a business free access)
- **past_due** — a payment failed
- **canceled** — stopped (use this to stop a business that hasn't paid)
- **expired** — the trial or paid period ran out (set automatically every hour)
A business can only switch AI employees on and assign work while trialing or active. Every status change is logged in Security monitoring.

## Behind the scenes (Render, Frankfurt)
| Render service | Job |
| --- | --- |
| ai-workforce-h0dp | The website |
| ai-workforce-worker-h0dp | Runs AI jobs in the background |
| ai-workforce-db-h0dp | Postgres database |
| ai-workforce-redis-h0dp | Job queue |
| ai-workforce-expiry-job-h0dp | Ends expired trials/periods hourly |
| ai-workforce-security-retention-h0dp | Clears old security logs nightly |
- The site updates itself about 2 minutes after each merge to `main` on GitHub.
- Settings live on each service's **Environment** page. Keys must be identical on the website and the worker; save with **Save, rebuild, and deploy**.
- Uploaded documents are stored encrypted in the AWS S3 bucket in Stockholm (eu-north-1). The AWS account is on a free plan that ends 19 May 2027 — upgrade before then or storage stops.
- Keep safe in a password manager (never in chat or GitHub): FILE_ENCRYPTION_KEY and INTEGRATION_ENCRYPTION_KEY (losing them makes stored data unreadable), OPENAI_API_KEY, the AWS access key, admin recovery codes.

## Google Drive integration (owner setup)
Businesses can import files they pick from Google Drive. It uses Google's narrowest permission (drive.file + the Google Picker), so no Google security audit is needed. It switches on once these four settings are on the website service (ai-workforce-h0dp → Environment): GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_API_KEY (Picker key, restricted to the site and the Google Picker API) and GOOGLE_APP_ID (the Google Cloud project number).
- Google Cloud project: Google Drive API and Google Picker API enabled; consent screen (External) with scopes drive.file, openid, userinfo.email; Web OAuth client with JavaScript origin https://ai-workforce-h0dp.onrender.com and redirect URI https://ai-workforce-h0dp.onrender.com/knowledge/integrations/google/callback.
- While the consent screen is in **Testing**, only listed test users can connect. Click **Publish app** to let every business connect; Google may ask to verify the app's name and logo (brand verification), which is free.
- Tokens are stored encrypted with INTEGRATION_ENCRYPTION_KEY; changing that key disconnects every business.

## Not set up yet
- **Email (SMTP)**: add SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM to the website service, so verification and password-reset emails send.
- **Online payments**: connect Paystack (best for mobile money in Ghana) or Stripe keys and webhooks. Until then, switch businesses on by hand (status **active**).
- **Inviting staff** to a workspace has no screen yet.
- **Business Email integration** is a placeholder (Google Drive is built; it needs the Google settings above).

## Troubleshooting
| What you see | What to do |
| --- | --- |
| 502 Bad Gateway | Wait 2 minutes; if it continues, open the web service's Logs on Render |
| "internal_server_error" with a request ID | Search that request ID in the web service's Logs |
| Jobs stuck on Queued | Check ai-workforce-worker-h0dp is Live and its logs; check Redis |
| "Invalid credentials or account temporarily locked" on /platform/login | Use the admin email; wait 15 minutes after 5 failures |
| Locked out of two-step codes | Use a recovery code; or re-run enable-platform-admin-mfa in the Render Shell |
| Customers get no emails | SMTP isn't configured yet |

## Privacy
Kombian only sees the question and this guide, never business records. Phone numbers, emails and long ID numbers are removed before questions reach the AI service.
