"""Credential envelope helpers. Provider OAuth callbacks and API execution are intentionally not enabled yet."""
import json
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _cipher():
    key = current_app.config.get("INTEGRATION_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY is not configured.")
    try:
        return Fernet(key.encode("ascii") if isinstance(key, str) else key)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def encrypt_credentials(credentials):
    if not isinstance(credentials, dict):
        raise ValueError("Credentials must be supplied as a dictionary.")
    raw = json.dumps(credentials, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return _cipher().encrypt(raw).decode("ascii")


def decrypt_credentials(ciphertext):
    if not ciphertext:
        return {}
    try:
        return json.loads(_cipher().decrypt(ciphertext.encode("ascii")).decode("utf-8"))
    except (InvalidToken, ValueError, TypeError) as exc:
        raise RuntimeError("Integration credentials could not be decrypted.") from exc
