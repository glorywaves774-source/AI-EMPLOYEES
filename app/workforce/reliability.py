"""Pure policy helpers for team workflow review and bounded recovery."""

REVIEWABLE_STATUS = "needs_review"
REVIEW_DECISIONS = {"approved", "rejected"}
RETRYABLE_STEP_STATUSES = {"failed", "blocked"}
MAX_RECOVERY_ATTEMPTS = 3


def validate_review_decision(decision, note):
    if decision not in REVIEW_DECISIONS:
        raise ValueError("Decision must be approved or rejected.")
    note = (note or "").strip()
    if len(note) > 1000:
        raise ValueError("Review note must be 1,000 characters or fewer.")
    if decision == "rejected" and not note:
        raise ValueError("A reason is required when rejecting a deliverable.")
    return decision, note


def retryable_step_keys(steps, max_attempts=MAX_RECOVERY_ATTEMPTS):
    """Return only failed/blocked steps below the bounded total-attempt ceiling."""
    return [step.step_key for step in steps
            if step.status in RETRYABLE_STEP_STATUSES and int(step.attempts or 0) < max_attempts]
