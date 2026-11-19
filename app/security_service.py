import hashlib, secrets, smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import pyotp
from flask import current_app
from .extensions import db, bcrypt
from .models import SecurityToken, User

def now(): return datetime.now(timezone.utc)

def as_utc(value):
    """Return value as an aware UTC datetime. SQLite drops tzinfo on
    DateTime(timezone=True) columns; PostgreSQL keeps it."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
def hash_token(raw): return hashlib.sha256(raw.encode()).hexdigest()

def issue_token(user_id, token_type, minutes):
    raw=secrets.token_urlsafe(48)
    db.session.add(SecurityToken(user_id=user_id, token_hash=hash_token(raw), token_type=token_type, expires_at=now()+timedelta(minutes=minutes)))
    return raw

def consume_token(raw, token_type):
    token=SecurityToken.query.filter_by(token_hash=hash_token(raw), token_type=token_type, used_at=None).first()
    if not token or as_utc(token.expires_at) <= now(): return None
    token.used_at=now(); db.session.flush(); return token

def send_email(to, subject, body):
    host=current_app.config.get("SMTP_HOST")
    if not host: return False
    msg=EmailMessage(); msg["From"]=current_app.config.get("SMTP_FROM") or current_app.config.get("SMTP_USERNAME")
    msg["To"]=to; msg["Subject"]=subject; msg.set_content(body)
    with smtplib.SMTP(host, current_app.config.get("SMTP_PORT",587), timeout=15) as smtp:
        if current_app.config.get("SMTP_USE_TLS", True): smtp.starttls()
        if current_app.config.get("SMTP_USERNAME"): smtp.login(current_app.config["SMTP_USERNAME"], current_app.config["SMTP_PASSWORD"])
        smtp.send_message(msg)
    return True

def setup_mfa(user):
    secret=pyotp.random_base32(); user.mfa_secret=secret; user.mfa_enabled=True
    codes=[secrets.token_hex(5) for _ in range(8)]; user.mfa_recovery_codes_json=[bcrypt.generate_password_hash(c).decode() for c in codes]
    return secret, codes

def verify_mfa(user, code):
    if not user.mfa_enabled or not user.mfa_secret: return False
    if pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1): return True
    for i,h in enumerate(user.mfa_recovery_codes_json or []):
        if bcrypt.check_password_hash(h, code):
            user.mfa_recovery_codes_json.pop(i); return True
    return False
