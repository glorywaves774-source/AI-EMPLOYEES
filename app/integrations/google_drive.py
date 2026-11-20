"""Google Drive connection: OAuth (drive.file + openid email only), token refresh,
and download of files a person picks with the Google Picker.

drive.file is a non-sensitive scope: the app can only open files the person
explicitly picks, so no restricted-scope security assessment is needed.
Tokens are stored encrypted with INTEGRATION_ENCRYPTION_KEY (vault.py).
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

from .vault import decrypt_credentials, encrypt_credentials

PROVIDER = "google_drive"
SCOPES = ["https://www.googleapis.com/auth/drive.file", "openid", "https://www.googleapis.com/auth/userinfo.email"]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files/"
CALLBACK_PATH = "/knowledge/integrations/google/callback"
MAX_BYTES = 12 * 1024 * 1024
MAX_FILES_PER_IMPORT = 10

# Google-native types are exported to a format the knowledge library can read.
EXPORTS = {
    "application/vnd.google-apps.document": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("text/plain", ".txt"),
}
DIRECT = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
}
PICKABLE_MIME_TYPES = ",".join(list(EXPORTS) + list(DIRECT))


class DriveError(Exception):
    """A user-facing problem talking to Google Drive."""


def is_configured():
    c = current_app.config
    return all(c.get(k) for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_API_KEY", "GOOGLE_APP_ID"))


def redirect_uri():
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    return base + CALLBACK_PATH


def _http(url, data=None, headers=None, method=None, raw=False, limit=None):
    body = urllib.parse.urlencode(data).encode() if isinstance(data, dict) else data
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method or ("POST" if body else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed https Google endpoints)
            payload = resp.read((limit + 1) if limit else -1)
            if limit and len(payload) > limit:
                raise DriveError("The file is larger than 12 MB.")
            return payload if raw else json.loads(payload or b"{}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read() or b"{}").get("error", "")
            if isinstance(detail, dict):
                detail = detail.get("message", "")
        except Exception:
            pass
        current_app.logger.warning("Google API error %s on %s: %s", exc.code, url.split("?")[0], str(detail)[:200])
        if exc.code in (401, 403) and "invalid_grant" not in str(detail):
            raise DriveError("Google refused access to that file. Pick it again, or reconnect Google Drive.") from exc
        if "invalid_grant" in str(detail):
            raise DriveError("The Google connection has expired or was removed. Reconnect Google Drive.") from exc
        if exc.code == 404:
            raise DriveError("That file wasn't found, or the app wasn't given access to it.") from exc
        raise DriveError("Google Drive didn't respond as expected. Please try again.") from exc
    except urllib.error.URLError as exc:
        raise DriveError("Couldn't reach Google. Please try again.") from exc


# ---------------------------------------------------------------- OAuth
def authorization_url(state):
    c = current_app.config
    q = {"client_id": c["GOOGLE_CLIENT_ID"], "redirect_uri": redirect_uri(), "response_type": "code",
         "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
         "include_granted_scopes": "true", "state": state}
    return AUTH_URL + "?" + urllib.parse.urlencode(q)


def exchange_code(code):
    c = current_app.config
    tok = _http(TOKEN_URL, {"code": code, "client_id": c["GOOGLE_CLIENT_ID"], "client_secret": c["GOOGLE_CLIENT_SECRET"],
                            "redirect_uri": redirect_uri(), "grant_type": "authorization_code"})
    granted = set((tok.get("scope") or "").split())
    if "https://www.googleapis.com/auth/drive.file" not in granted:
        raise DriveError("Google Drive access wasn't granted. Tick the Drive box on Google's screen and try again.")
    if not tok.get("refresh_token"):
        raise DriveError("Google didn't return a lasting connection. Disconnect the app in your Google account and try again.")
    email = ""
    try:
        email = _http(USERINFO_URL, headers={"Authorization": f"Bearer {tok['access_token']}"}).get("email", "")
    except DriveError:
        pass
    return {"refresh_token": tok["refresh_token"], "access_token": tok["access_token"],
            "expires_at": int(time.time()) + int(tok.get("expires_in", 3600)), "scope": tok.get("scope", "")}, email


def access_token(connection):
    """A valid access token for this connection, refreshing (and re-encrypting) when needed."""
    creds = decrypt_credentials(connection.credential_ciphertext)
    if not creds.get("refresh_token"):
        raise DriveError("Google Drive isn't connected.")
    if creds.get("access_token") and creds.get("expires_at", 0) > time.time() + 90:
        return creds["access_token"], creds["expires_at"]
    c = current_app.config
    tok = _http(TOKEN_URL, {"client_id": c["GOOGLE_CLIENT_ID"], "client_secret": c["GOOGLE_CLIENT_SECRET"],
                            "refresh_token": creds["refresh_token"], "grant_type": "refresh_token"})
    creds["access_token"] = tok["access_token"]
    creds["expires_at"] = int(time.time()) + int(tok.get("expires_in", 3600))
    connection.credential_ciphertext = encrypt_credentials(creds)
    return creds["access_token"], creds["expires_at"]


def revoke(connection):
    """Best effort: tell Google to drop the grant."""
    try:
        creds = decrypt_credentials(connection.credential_ciphertext)
        token = creds.get("refresh_token") or creds.get("access_token")
        if token:
            _http(REVOKE_URL, {"token": token})
    except Exception:
        current_app.logger.info("Google token revoke did not complete; the stored token is deleted anyway")


# ---------------------------------------------------------------- files
def download(token, file_id):
    """Return (filename, bytes) for a picked file, exporting Google Docs/Sheets/Slides."""
    if not file_id or not all(ch.isalnum() or ch in "-_" for ch in file_id) or len(file_id) > 200:
        raise DriveError("That doesn't look like a Google Drive file.")
    auth = {"Authorization": f"Bearer {token}"}
    meta = _http(DRIVE_FILES + file_id + "?fields=id,name,mimeType,size&supportsAllDrives=true", headers=auth)
    name, mime = meta.get("name") or "drive-file", meta.get("mimeType", "")
    if mime in EXPORTS:
        export_mime, ext = EXPORTS[mime]
        data = _http(DRIVE_FILES + file_id + "/export?" + urllib.parse.urlencode({"mimeType": export_mime}),
                     headers=auth, raw=True, limit=MAX_BYTES)
    elif mime in DIRECT:
        ext = DIRECT[mime]
        if int(meta.get("size") or 0) > MAX_BYTES:
            raise DriveError(f"“{name}” is larger than 12 MB.")
        data = _http(DRIVE_FILES + file_id + "?alt=media&supportsAllDrives=true", headers=auth, raw=True, limit=MAX_BYTES)
    else:
        raise DriveError(f"“{name}” is a type the knowledge library can't read. Use PDF, Word, text, Markdown, CSV or Google Docs/Sheets/Slides.")
    if not name.lower().endswith(ext):
        name += ext
    return name, data
