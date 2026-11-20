# AI Workforce — help guide for business workspaces

Page references are written like [[page:billing]]. Kombian turns them into links only for people whose role can open that page.

## What AI Workforce is
AI Workforce gives a business a private workspace with a team of AI employees. You give the team a job in plain words; the AI Team Coordinator splits it up, chooses up to 4 active specialists, collects their parts and writes one combined result. Every result is a draft for a person to check. The AI never sends emails, makes payments or takes any action outside the app.

Each business's workspace is private: other businesses can never see its employees, jobs or documents.

## Roles in a workspace
- **Owner** — the person who created the workspace. Can do everything, including exporting all workspace data.
- **Admin** — everything except exporting workspace data: changes the plan, deletes documents, approves or rejects requests, requests integrations.
- **Manager** — assigns work, switches AI employees on/off, creates departments and AI employees, uploads documents and sets AI access, sees Analytics, submits approval requests.
- **Employee** — can view the dashboard, jobs, approvals, knowledge, integrations and billing, and set up two-step sign-in, but cannot change anything else.

There is no screen for inviting staff yet, so today each workspace has one user: its Owner.

## Signing up and signing in
1. Open the business sign-up page (/auth/register). Enter full name, work email, business name and a password of at least 12 characters, then tap **Create workspace**.
2. You land on [[page:home]] straight away. The **14-day free trial** starts immediately, with all ten starter AI employees already switched on and ready for work.
3. Next time, sign in at /auth/login. Five wrong passwords lock the account for 15 minutes.
4. **Forgot password?** on the sign-in page sends a reset link (only once the platform owner has set up email).
5. The platform owner's admin account is separate and does NOT work on the business sign-in page.

## The starting team
Every new workspace gets 9 departments and 10 AI employees, all starting as **Draft** (switched off):
| AI employee | Department |
| --- | --- |
| AI Team Coordinator | Executive Office |
| AI Executive Assistant | Executive Office |
| AI Human Resource Officer | Human Resources |
| AI Accountant | Finance |
| AI Marketing Officer | Marketing |
| AI Customer Service Officer | Customer Service |
| AI Operations Manager | Operations |
| AI Project Manager | Projects |
| AI Research Officer | Research |
| AI Software Developer | Technology |

## Switching AI employees on or off
New workspaces start with the whole team active, so you can assign work at once. Assignments need the **AI Team Coordinator** plus at least one specialist to be Active.
1. On [[page:home]], scroll to **AI employees**.
2. On the **AI Team Coordinator** card, change the menu at the bottom from **Draft** to **Active**. The page reloads and the badge turns green.
3. Do the same for one or more specialists who fit the work.
- Statuses: **Draft** (set up, not working), **Active** (can be given work), **Paused** (temporarily off; frees a place).
- Active employees allowed at once: **free trial 10**, **Starter 3**, **Growth 10**, **Business 30**. The Coordinator counts as one.
- When a trial becomes a paid Starter plan, pause employees until no more than 3 are Active; assignments are blocked until then.
- **Edit details** on an employee card changes its name, job title, department and description (Owners, Admins, Managers). A clear description helps the Coordinator give it the right work.
- If you see "Activate the Team Coordinator and at least one specialist before assigning work", switch them on first.
- If you see "Your … plan allows up to N active AI employees", pause one or upgrade on [[page:billing]].
- Owners, Admins and Managers can change statuses.

## Adding departments and AI employees
1. On [[page:home]], use **Add department**: a name (1–100 characters) and description, then **Create department**.
2. Use **Create AI employee**: name (e.g. AI Legal Officer), job title, department and responsibilities, then **Create draft employee**.
3. New employees start as Draft; switch to Active when ready.
A clear job title and description matter: the Coordinator picks specialists by matching words in your assignment against each active employee's job title, name and description.

## Giving the team a job (assignments)
1. On [[page:home]], find **Assign work to your AI team**.
2. **Assignment title**: a short name, e.g. "Prepare Q4 cash-flow summary".
3. **Assignment details** (up to 8,000 characters): the goal, the facts the team needs, limits, and the format you want back. Specific briefs get better results.
4. Tap **Send assignment to AI workforce**. The job appears under **Recent assignments**; tap it to open its page and reload to see progress.

Job statuses: **Queued** (waiting), **Running** (specialists working), **Needs review** (done, awaiting a person's approval), **Completed**, **Failed** (see the message on its page), **Cancelled**.

On a job's page: the brief, the Coordinator's plan, each specialist's contribution and the combined result.
- **Approve deliverable** / **Reject deliverable** (with an optional note) records your decision only.
- **Cancel assignment** stops a queued job at once; a running job stops after its current step.
- **Retry eligible failed steps** re-runs only the failed parts; finished parts are kept.

Every job counts towards the task allowance: **Starter 100**, **Growth 500**, **Business 2,000** per billing period. During the free trial there is also a daily allowance of **5 assignments a day**, renewed at midnight (GMT), so the trial lasts the full 14 days; the dashboard shows how many are left today. Jobs that fail because the AI service itself was unavailable are **not** counted. A job stuck on Queued usually means the background worker is down — tell the platform owner.

## Templates, repeating assignments and downloads
- **Start from a template** (above the assignment form on [[page:home]]) fills in a ready-made assignment: marketing plan, social media posts, complaint reply, customer FAQ, job advert, staff policy, cash-flow forecast, pricing, proposal, competitor check, procedures (SOP) or donor report. Replace everything in [square brackets] with your own details; the app won't send it until you do.
- **Repeat**: choose Every day, Every week or Every month and a time (Ghana time) before sending. The team then does the assignment again automatically; each run counts towards your allowance. See, pause or delete them under **Repeating assignments** on [[page:home]].
- **Download Word** on a finished assignment gives a .docx file; **Download Excel** appears when the response contains tables and gives an .xlsx with real numbers you can calculate with.
- When email is set up, the person who sent an assignment gets an email when it's ready (or if it couldn't be finished).

## Team members
Owners and Admins open [[page:team]] to invite colleagues by email with a role: **Admin** (everything except data export; only the Owner can invite Admins), **Manager** (assigns work, manages AI employees and documents) or **Employee** (views work and documents). If email isn't set up, you get a link to send by WhatsApp or SMS; it works once, for 7 days. You can change roles or remove people at any time; their past work stays.

## Website chat (customer chatbot)
Owners and Admins open [[page:website_chat]] to put a chat button on the business's own website:
1. Give the **Customer Service Officer** access to a knowledge folder with your prices, opening hours, delivery and FAQs (the chatbot answers only from those documents).
2. Set the chatbot's name, greeting, what to tell customers when it doesn't know (e.g. your phone/WhatsApp), and your website address.
3. Use **Preview** to try it, then **Turn on**.
4. Copy the one-line code and paste it before </body> on your website (or send it to your web designer).
Every chat appears under **Recent customer chats**. It never takes payments, orders or promises. Free trial: 100 answers a day; paid plans: 1,000. WhatsApp needs a verified Meta business account; ask Kayron.

## Charts, presentations and graphics
When an assignment is **Completed**, open it and scroll to **Turn this into visuals** (Owners, Admins, Managers):
- **Charts**: bar, line or pie charts of the figures in the response, as PNG images. If the response has no figures, you'll be told so.
- **Presentation**: a PowerPoint (.pptx) deck with speaker notes and charts, in your business name. Opens in PowerPoint, Google Slides or Keynote.
- **Graphic**: a flyer, social media post, banner or infographic. **Design** style gives an editable SVG (opens in a browser, Canva, Illustrator or Inkscape). **Photo-style image** gives a PNG and only works when the platform owner has set up OpenAI.
- Optionally say what you want (e.g. "8 slides for our board", "Instagram post announcing our launch"), then tap the button. Files take about a minute; refresh the page to see them.
- Every file starts as a **Draft**. Owners and Admins can **Approve** or **Reject** it; this only records a decision, nothing is posted or sent.
- Free trial: 5 visuals a day. Paid plans: up to 40 a day.
- Charts only use figures from the response; estimates are labelled "Estimated". Always check numbers before sharing.

## Approvals
[[page:approvals]] is the record of who signed off on what. Approving only records a decision; nothing is carried out automatically.
- **Request approval**: enter an **Action type** (e.g. "Supplier payment over GHS 10,000") and a **Description**, then **Submit for approval**. Owners, Admins and Managers can submit.
- **Decide**: under **Approval requests**, add an optional **Decision note** and tap **Approve** or **Reject**. Only Owners and Admins can decide.
- **AI deliverables awaiting review** lists jobs whose results need approving.

## Business knowledge (documents)
On [[page:knowledge]] you upload your own documents so AI employees can use them as reference. Files are stored encrypted in private storage.
- **Create a repository** (a folder): name and description, then **Create repository**.
- **Upload a document**: **Choose file** (PDF, DOCX, TXT, MD or CSV, up to 12 MB), pick the repository, then **Upload and index**. The text is extracted so it can be searched.
- **Give AI employees access**: open the repository's access page, tick the AI employees that may read it, then **Save access permissions**. Access is off until granted, and every read by an AI employee is logged.
- **Search** finds matching passages across documents. Each document has **Download** and **Delete** (delete is permanent and removes its searchable text).
- Owners, Admins and Managers create repositories, upload and set access; only Owners and Admins delete.

## Integrations (Google Drive)
On [[page:integrations]] you can bring files from Google Drive into the knowledge library. AI Workforce can only open the files you pick with Google's file picker, never the rest of your Drive.
**Connect (Owner or Admin):**
1. Open [[page:integrations]] and tap **Connect Google Drive**.
2. Choose your Google account and allow access to "files you choose" on Google's screen.
3. You return to the page, which now shows **connected** and the Google account.
**Import files (Owner, Admin or Manager):**
1. Create a knowledge folder first on [[page:knowledge]] if you have none.
2. On [[page:integrations]], pick the folder under **Import into knowledge folder**.
3. Tap **Import from Google Drive**, select up to 10 files in Google's picker and confirm.
4. The page lists what was imported and what wasn't (with the reason). Then grant AI employees access to that folder, as with uploads.
- Supported: PDF, Word (.docx), text, Markdown, CSV, and Google Docs (imported as Word), Sheets (first sheet as CSV) and Slides (as text). Up to 12 MB each.
- Imported files are copies: later changes in Drive don't update them — import again to refresh.
- **Disconnect Google Drive** (Owner or Admin) removes the connection; files already imported stay.
- If the card says **not available yet**, the platform owner hasn't finished the Google setup; an Owner or Admin can tap **Request setup** to register interest.
- "Google refused access" or "connection has expired": tap **Disconnect Google Drive**, then **Connect Google Drive** again.
Business Email is not available yet; an Owner or Admin can tap **Request setup** on its card to register interest.

## Analytics
[[page:analytics]] (Owners, Admins, Managers) shows, for the last 7, 30, 90 or 365 days: tasks created, completed, failed, queued/running; AI usage and estimated AI cost; workforce health (active AI employees, pending approvals, knowledge documents); and each AI employee's activity. The export button downloads the figures as a CSV file for Excel or Google Sheets.

## Plans, billing and payments
Plans (prices set by the platform owner, in GHS per month):
| Plan | Price | Active AI employees | Tasks per period |
| --- | --- | --- | --- |
| Starter | GHS 450 | 3 | 100 |
| Growth | GHS 2,200 | 10 | 500 |
| Business | GHS 8,500 | 30 | 2,000 |
Every new workspace starts on a **14-day free trial**: the whole team of up to 10 active AI employees, 5 assignments a day. Afterwards, choose a plan to continue.

On [[page:billing]]: current plan, limits, tasks used this period and when the trial or period ends.
- **Upgrade**: tap **Subscribe** (during the trial) or **Choose plan** and pay with **Mobile Money (MTN MoMo, Telecel Cash, AT Money) or card** on Paystack's page; you pay on the provider's page and the plan switches on after payment is confirmed. (Online payment works only once the platform owner has connected Paystack or Stripe.)
- **Cancel at period end** stops renewal; access continues until the date shown. You can undo it before then.
- **Payment history** and **Invoices** list past payments.
- Only Owners and Admins can change or cancel the plan.
- "Your subscription is not active. Choose a plan to continue." means the trial or paid period ended or was cancelled.

## Account security
- **Two-step sign-in**: open [[page:security]], tap **Start setup**, add the key to an authenticator app (Google Authenticator, Microsoft Authenticator) using "Enter a setup key", enter the current code and **save the recovery codes** shown (each works once).
- After that, signing in asks for the 6-digit code; a recovery code works in its place.
- Passwords need at least 12 characters.
- The Owner can download a copy of workspace data (members, AI employees, jobs) from [[page:export]].

## Look and layout
- **Dark mode / Light mode** button at the top right of every page; the choice is remembered on that device.
- On phones: Home, Approvals, Knowledge and Analytics are in the bottom bar; **Menu** holds the other pages, the theme switch and Sign out.
- **Sign out**: top right on a computer, inside Menu on a phone.

## Troubleshooting
| What you see | What to do |
| --- | --- |
| Employee stays on Draft after choosing Active | Reload; if it persists the site update may not be live yet — tell the platform owner |
| "Activate the Team Coordinator and at least one specialist" | Switch them to Active on [[page:home]] |
| "Your plan allows up to N active AI employees" | Pause one or upgrade on [[page:billing]] |
| "Your subscription is not active" | Choose a plan on [[page:billing]], or ask the platform owner |
| Job stuck on Queued | The background worker may be down; tell the platform owner |
| Job Failed | Open it, read the message, tap **Retry eligible failed steps** |
| "The AI service is temporarily unavailable" | A problem on the platform side (Kayron is alerted). It is not counted against your allowance; try again later |
| "Charts … can be made once the assignment is completed" | Wait for the assignment to finish, then try again |
| "This assignment has no figures that can be charted" | Try a presentation or graphic instead, or ask for an assignment with numbers |
| "Your free trial includes 5 assignments a day" | The daily trial allowance is used up; it renews at midnight (GMT), or choose a plan |
| "Free-trial capacity for today is fully booked" | Trial capacity is shared and renews at midnight (GMT), or choose a plan |
| "Invalid credentials or account temporarily locked" | Check you're on the business sign-in page and the password; wait 15 minutes after 5 failures |
| No verification or reset email | Email isn't set up yet; ask the platform owner |
| 502 Bad Gateway | The site is restarting; wait 2 minutes |
| "internal_server_error" with a request ID | Send the request ID to the platform owner |

## Privacy
Kombian only sees your question and this guide. It never sees your documents, jobs, employees or other records. Phone numbers, email addresses and long ID numbers are removed from questions before they're sent to the AI service.
