"""Reading the sandbox settings (the single row in the sandbox_settings table)."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import SandboxSettings


def get_settings(db: Session) -> SandboxSettings:
    """Return the settings row, creating it with default values the first time."""
    settings = db.get(SandboxSettings, 1)
    if settings is None:
        db.add(SandboxSettings(id=1))
        try:
            db.commit()
        except IntegrityError:  # another request created it at the same moment
            db.rollback()
        settings = db.get(SandboxSettings, 1)
    return settings
