"""Tests for the shared page shell: theme switching, phone navigation, CSP safety."""
import os
import re
import tempfile
import unittest

from app import create_app
from app.extensions import db


class UiShellTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()

        class TestConfig:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name.replace("\\", "/")
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = False
            RATELIMIT_ENABLED = False
            CELERY_BROKER_URL = "memory://"
            CELERY_RESULT_BACKEND = "cache+memory://"
            RATELIMIT_STORAGE_URI = "memory://"
            PUBLIC_BASE_URL = "http://localhost"
            STORAGE_BACKEND = "local"

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        os.unlink(self.tmp.name)

    def _register(self):
        r = self.client.post("/auth/register", data={
            "full_name": "Owner Person", "email": "owner@example.com",
            "business_name": "Example Ltd", "password": "a-very-strong-password-123", "accept_terms": "yes",
        })
        self.assertIn(r.status_code, (302, 303))

    def _html(self, path):
        r = self.client.get(path)
        self.assertEqual(r.status_code, 200, path)
        return r.get_data(as_text=True)

    def test_theme_script_runs_before_stylesheets(self):
        html = self._html("/auth/login")
        head = html.split("</head>")[0]
        self.assertIn("js/theme.js", head)
        self.assertLess(head.index("js/theme.js"), head.index("css/app.css"))
        self.assertLess(head.index("css/app.css"), head.index("css/mobile.css"), "mobile.css must load last")
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1', head)

    def test_theme_toggle_on_public_and_signed_in_pages(self):
        self.assertIn("data-theme-toggle", self._html("/auth/login"))
        self.assertIn("data-theme-toggle", self._html("/platform/login"))
        self._register()
        self.assertIn("data-theme-toggle", self._html("/dashboard"))

    def test_no_inline_scripts_so_csp_holds(self):
        pages = [self._html("/auth/login")]
        self._register()
        pages += [self._html(p) for p in ("/dashboard", "/billing/", "/knowledge/integrations")]
        for path, html in zip(("/auth/login", "/dashboard", "/billing/", "/knowledge/integrations"), pages):
            for tag in re.findall(r"<script\b[^>]*>", html):
                self.assertIn("src=", tag, f"inline <script> on {path}: {tag}")
        csp = self.client.get("/healthz").headers.get("Content-Security-Policy", "")
        if csp:
            self.assertNotIn("'unsafe-inline'", csp.split("script-src")[1].split(";")[0])

    def test_templates_have_no_inline_event_handlers(self):
        # CSP script-src 'self' silently blocks onclick=/onchange= etc.
        import pathlib
        offenders = []
        for f in pathlib.Path(self.app.root_path, "templates").rglob("*.html"):
            for m in re.finditer(r"\son[a-z]+\s*=\s*[\"']", f.read_text()):
                offenders.append(f"{f.name}: {m.group(0).strip()}")
        self.assertEqual(offenders, [])

    def test_static_assets_are_served(self):
        for asset in ("css/app.css", "css/mobile.css", "js/theme.js", "js/ui.js"):
            r = self.client.get(f"/static/{asset}")
            self.assertEqual(r.status_code, 200, asset)
            r.close()

    def test_visitors_get_no_tab_bar_or_menu(self):
        html = self._html("/auth/login")
        self.assertNotIn('class="tabbar"', html)
        self.assertNotIn('id="drawer"', html)

    def test_signed_in_users_get_tab_bar_menu_and_current_page(self):
        self._register()
        html = self._html("/billing/")
        self.assertIn('class="tabbar"', html)
        self.assertIn('id="drawer"', html)
        # 4 destinations + Menu, never actions
        tabbar = html.split('class="tabbar"')[1].split("</nav>")[0]
        self.assertEqual(tabbar.count("<a "), 4)
        self.assertIn("data-menu-open", tabbar)
        # current page is marked in the drawer and desktop nav
        self.assertRegex(html, r'href="/billing/"\s+aria-current="page"')
        dash = self._html("/dashboard")
        tabbar = dash.split('class="tabbar"')[1].split("</nav>")[0]
        self.assertRegex(tabbar, r'href="/dashboard"\s+aria-current="page"')

    def test_platform_pages_do_not_show_workspace_navigation(self):
        html = self._html("/platform/login")
        self.assertNotIn('class="tabbar"', html)
        self.assertNotIn("desktop-nav", html)

    def test_billing_page_allows_redirect_to_checkout_only_there(self):
        self._register()
        csp = self.client.get("/billing/").headers["Content-Security-Policy"]
        form_action = csp.split("form-action")[1].split(";")[0]
        self.assertIn("https://checkout.paystack.com", form_action)
        self.assertIn("https://checkout.stripe.com", form_action)
        self.assertIn("script-src 'self';", csp)
        self.assertNotIn("checkout.paystack.com", self.client.get("/dashboard").headers["Content-Security-Policy"])

    def test_login_links_to_password_reset(self):
        self.assertIn('href="/auth/forgot-password"', self._html("/auth/login"))


if __name__ == "__main__":
    unittest.main()
