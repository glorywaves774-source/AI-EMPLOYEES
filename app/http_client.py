"""Identity sent with the app's own server-to-server requests.

Some providers sit behind firewalls (e.g. Cloudflare) that reject Python's default
"Python-urllib" signature with HTTP 403 / error 1010 before the request reaches
the API, so every outgoing request names the app explicitly.
"""
USER_AGENT = "AI-Workforce/1.0 (Kayron Global Tech Services; +https://ai-workforce-h0dp.onrender.com)"


def headers(extra=None):
    return {"User-Agent": USER_AGENT, "Accept": "application/json", **(extra or {})}
