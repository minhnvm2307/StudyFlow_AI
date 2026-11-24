"""Default values used when initialising new DB records."""
import re
import fsrs


def email_to_user_id(email: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", email.lower()).strip("-")
    return f"user-{slug}"


def default_fsrs_card() -> dict:
    return fsrs.Card().to_dict()


DEFAULT_STUDY_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
DEFAULT_DAILY_GOAL_MINUTES = 30
DEFAULT_MASCOT_TONE = "encouraging"
