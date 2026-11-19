# Milestone 7 — Workforce Analytics & Operational Intelligence

- Tenant-scoped dashboard for 7, 30, 90 and 365 day reporting periods.
- Task completion, failure and queue metrics.
- Agent run and token totals, employee activity breakdown.
- Pending approvals, active AI employee and knowledge-document snapshots.
- CSV export for the selected period.
- Optional estimated token costs, disabled by default. Configure model-specific per-million-token rates; estimates are not invoices and may omit cached/reasoning tokens or other charges.

Analytics and exports are restricted to owners, admins and managers. All detailed queries are tenant-filtered. No database schema changes are introduced. Full runtime validation requires the project dependencies and a configured test database.
