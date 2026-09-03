"""Helpers for database-backed, site-wide settings."""

from sqlalchemy.orm import Session

from app.models import SystemSetting


REGISTRATION_ENABLED_KEY = "registration_enabled"
REQUIRE_ADMIN_APPROVAL_KEY = "require_admin_approval"


def get_bool(db: Session, key: str, default: bool) -> bool:
    """Return a boolean setting, falling back when it has never been saved."""
    row = db.get(SystemSetting, key)
    if row is None:
        return default
    return row.value.strip().lower() in {"1", "true", "yes", "on"}


def set_bool(db: Session, key: str, value: bool) -> None:
    row = db.get(SystemSetting, key)
    text = "true" if value else "false"
    if row is None:
        db.add(SystemSetting(key=key, value=text))
    else:
        row.value = text
