"""AI providers behind one call: Claude (Anthropic) and OpenAI.

`complete()` tries the preferred provider first and moves to the other one when
the first refuses for a platform-side reason (no credit, bad key, unknown
model) or is overloaded. Only text goes out; no tools or external actions.

Settings (Render environment):
  AI_PROVIDER         auto | claude | openai   (auto = Claude first when its key is set)
  ANTHROPIC_API_KEY   enables Claude
  CLAUDE_MODEL        paying workspaces      (default claude-sonnet-5-5)
  TRIAL_CLAUDE_MODEL  free-trial workspaces  (default claude-haiku-5-5)
  OPENAI_API_KEY, OPENAI_MODEL, TRIAL_OPENAI_MODEL  as before
"""
import os

from flask import current_app

DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"
DEFAULT_TRIAL_CLAUDE_MODEL = "claude-haiku-5-5"
DEFAULT_OPENAI_MODEL = "gpt-5.5"


class AIServiceUnavailable(RuntimeError):
    """Every configured provider refused for a platform-side reason.

    Retrying does not help and the client did nothing wrong, so these failures
    are never retried and never counted against a workspace's allowance.
    `refs` (e.g. ["claude-credit", "openai-key"]) tell the platform owner why.
    """

    def __init__(self, message, refs=()):
        super().__init__(message)
        self.refs = list(refs)


class _Refused(Exception):
    def __init__(self, ref, detail):
        super().__init__(detail)
        self.ref = ref


def _cfg(name, default=None):
    value = current_app.config.get(name)
    if value in (None, ""):
        value = os.environ.get(name)
    return default if value in (None, "") else value


def _openai_key():
    return _cfg("OPENAI_API_KEY")


def _claude_key():
    return _cfg("ANTHROPIC_API_KEY")


def provider_order():
    """Configured providers, preferred first."""
    available = [p for p, key in (("claude", _claude_key()), ("openai", _openai_key())) if key]
    preferred = str(_cfg("AI_PROVIDER", "auto")).lower()
    if preferred == "openai":
        available.sort(key=lambda p: p != "openai")
    return available


def any_provider_configured():
    return bool(provider_order())


def model_for(provider, trial=False):
    if provider == "claude":
        if trial:
            return _cfg("TRIAL_CLAUDE_MODEL", DEFAULT_TRIAL_CLAUDE_MODEL)
        return _cfg("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)
    if trial and _cfg("TRIAL_OPENAI_MODEL"):
        return _cfg("TRIAL_OPENAI_MODEL")
    return _cfg("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)


# --- clients (module-level so tests can patch them) -------------------------
def openai_client():
    from openai import OpenAI
    return OpenAI(api_key=_openai_key(), timeout=90.0, max_retries=2)


def claude_client():
    import anthropic
    return anthropic.Anthropic(api_key=_claude_key(), timeout=120.0, max_retries=2)


# --- classification of provider errors --------------------------------------
_OPENAI_FAULTS = {"insufficient_quota": "credit", "credit_balance_exhausted": "credit",
                  "billing_hard_limit": "credit", "invalid_api_key": "key",
                  "account_deactivated": "key", "model_not_found": "model"}
_CLAUDE_FAULT_CLASSES = {"PaymentRequiredError": "credit", "EnforcedSpendLimitReachedError": "credit",
                         "ContractSpendLimitReachedError": "credit", "OrganizationOnHoldError": "credit",
                         "LinkedOrganizationSpendLimitReachedError": "credit",
                         "AuthenticationError": "key", "PermissionDeniedError": "key",
                         "NotFoundError": "model"}
_TRANSIENT_CLASSES = {"OverloadedError", "ServiceUnavailableError", "InternalServerError"}


def _classify(provider, exc):
    """Return a ref like 'claude-credit' for platform-side refusals, 'busy' for overload, else None."""
    detail = str(exc)
    name = type(exc).__name__
    if provider == "openai":
        for code, kind in _OPENAI_FAULTS.items():
            if code in detail:
                return f"openai-{kind}"
    else:
        if name in _CLAUDE_FAULT_CLASSES:
            return f"claude-{_CLAUDE_FAULT_CLASSES[name]}"
        lowered = detail.lower()
        if "credit balance" in lowered or "billing" in lowered:
            return "claude-credit"
    if name in _TRANSIENT_CLASSES:
        return f"{provider}-busy"
    return None


# --- calls -------------------------------------------------------------------
def _call_openai(model, instructions, input_text, max_tokens):
    response = openai_client().responses.create(model=model, instructions=instructions, input=input_text,
                                                max_output_tokens=max_tokens, store=False)
    usage = getattr(response, "usage", None)
    return ((getattr(response, "output_text", "") or "").strip(),
            int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0))


def _call_claude(model, instructions, input_text, max_tokens):
    response = claude_client().messages.create(model=model, max_tokens=max_tokens, system=instructions,
                                               messages=[{"role": "user", "content": input_text}])
    text = "".join(getattr(block, "text", "") for block in (response.content or [])
                   if getattr(block, "type", "") == "text").strip()
    usage = getattr(response, "usage", None)
    return text, int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)


_CALLERS = {"openai": _call_openai, "claude": _call_claude}


def complete(instructions, input_text, *, trial=False, max_tokens=None):
    """Return (text, model, input_tokens, output_tokens) from the first provider that answers."""
    from app.billing.services import AI_SERVICE_UNAVAILABLE
    max_tokens = int(max_tokens or _cfg("OPENAI_MAX_OUTPUT_TOKENS", 3000))
    providers = provider_order()
    if not providers:
        raise AIServiceUnavailable(
            f"{AI_SERVICE_UNAVAILABLE}. No AI provider is set up yet; Kayron has been alerted. "
            "This assignment was not counted against your allowance. (ref: no-provider)", ["no-provider"])
    refs = []
    for index, provider in enumerate(providers):
        model = model_for(provider, trial)
        try:
            text, tokens_in, tokens_out = _CALLERS[provider](model, instructions, input_text, max_tokens)
        except Exception as exc:
            ref = _classify(provider, exc)
            if ref is None:
                # Unexpected refusal: log the provider's own reason (never the key) so it can be fixed.
                current_app.logger.error("AI provider %s error %s (model %s): %s", provider,
                                         type(exc).__name__, model, str(exc)[:500])
                raise
            refs.append(ref)
            current_app.logger.error("AI provider %s refused (%s): %s", provider, ref, str(exc)[:300])
            if index + 1 < len(providers):
                current_app.logger.warning("Switching to the next AI provider.")
            continue
        if not text:
            raise RuntimeError("The AI service returned an empty response.")
        return text, model, tokens_in, tokens_out
    raise AIServiceUnavailable(
        f"{AI_SERVICE_UNAVAILABLE}. Kayron has been alerted. This assignment was not counted against "
        f"your allowance; please try again later. (ref: {', '.join(refs)})", refs)
