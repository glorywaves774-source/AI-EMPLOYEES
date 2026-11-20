"""Public legal pages: privacy policy and terms of use (no sign-in needed)."""
from flask import Blueprint, current_app, render_template

legal_bp = Blueprint("legal", __name__)
LEGAL_VERSION = "2026-11-20"


def _contact():
    cfg = current_app.config
    return {
        "company": cfg.get("PLATFORM_NAME", "Kayron Global Tech Services"),
        "address": cfg.get("LEGAL_ADDRESS", "NX-0000-9674 (GhanaPost GPS), Saboba, Northern Region, Ghana"),
        "phone": cfg.get("LEGAL_PHONE", "0539926867"),
        "whatsapp": cfg.get("LEGAL_WHATSAPP", "0596740151"),
        "email": cfg.get("LEGAL_EMAIL") or "",
        "updated": "20 November 2026",
    }


@legal_bp.get("/privacy")
def privacy():
    return render_template("legal/privacy.html", c=_contact())


@legal_bp.get("/terms")
def terms():
    return render_template("legal/terms.html", c=_contact())
