"""Single registry of the app's pages and who may open them.

Used by the navigation (so people only see pages they can open) and by
Kombian (so it only offers links the asker's role can follow).
Roles mirror the route guards in each blueprint.
"""

ALL_MEMBERS = frozenset({"owner", "admin", "manager", "employee"})
MANAGERS = frozenset({"owner", "admin", "manager"})
ADMINS = frozenset({"owner", "admin"})
OWNER = frozenset({"owner"})

# key: (label, endpoint, roles allowed to OPEN the page, what you do there)
WORKSPACE_PAGES = {
    "home": ("Home", "workspace.dashboard", ALL_MEMBERS, "assign work, see recent jobs, switch AI employees on or off"),
    "approvals": ("Approvals", "approvals.index", ALL_MEMBERS, "review AI results and sign-off requests"),
    "knowledge": ("Knowledge", "knowledge.index", ALL_MEMBERS, "upload documents, folders, search, AI access"),
    "integrations": ("Integrations", "knowledge.integrations", ALL_MEMBERS, "connect Google Drive and import picked files into a knowledge folder"),
    "analytics": ("Analytics", "analytics.index", MANAGERS, "task, usage and cost figures; CSV export"),
    "billing": ("Billing", "billing.index", ALL_MEMBERS, "plan, usage, payments; Owners/Admins change the plan"),
    "website_chat": ("Website chat", "widget.manage", ADMINS, "set up a customer chatbot for your own website, copy its code, read chats"),
    "team": ("Team", "team.index", ADMINS, "invite colleagues, change their roles or remove access"),
    "security": ("Two-step sign-in", "auth.mfa_setup", ALL_MEMBERS, "turn on authenticator codes for your account"),
    "export": ("Data export", "workspace.export_tenant_data", OWNER, "download a copy of the workspace data"),
}

# Things a role can SEE but not DO: (page key, action, roles allowed)
WORKSPACE_ACTIONS = {
    "assign work": MANAGERS,
    "switch AI employees on or off": MANAGERS,
    "create departments or AI employees": MANAGERS,
    "upload documents or set AI access": MANAGERS,
    "delete documents": ADMINS,
    "request integration setup": ADMINS,
    "connect or disconnect Google Drive": ADMINS,
    "import files from Google Drive": MANAGERS,
    "approve or reject sign-off requests": ADMINS,
    "change or cancel the plan": ADMINS,
    "export workspace data": OWNER,
    "invite or remove team members": ADMINS,
}

PLATFORM_PAGES = {
    "admin": ("SaaS Administration Centre", "platform.dashboard", frozenset({"platform_admin"}), "plans, prices, businesses, subscriptions, payments, security log"),
}

NAV_ORDER = ["home", "approvals", "knowledge", "integrations", "website_chat", "analytics", "team", "billing"]
TAB_KEYS = ["home", "approvals", "knowledge", "analytics"]


def pages_for(role):
    """Pages the given role can open: {key: (label, endpoint, description)}."""
    if role == "platform_admin":
        return {k: (v[0], v[1], v[3]) for k, v in PLATFORM_PAGES.items()}
    return {k: (v[0], v[1], v[3]) for k, v in WORKSPACE_PAGES.items() if role in v[2]}


def all_page_labels():
    """Every page key -> label, including ones the asker cannot open."""
    out = {k: v[0] for k, v in WORKSPACE_PAGES.items()}
    out.update({k: v[0] for k, v in PLATFORM_PAGES.items()})
    return out


def roles_for_page(key):
    if key in WORKSPACE_PAGES:
        return WORKSPACE_PAGES[key][2]
    if key in PLATFORM_PAGES:
        return PLATFORM_PAGES[key][2]
    return frozenset()
