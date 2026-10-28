from __future__ import annotations

import hashlib
import hmac

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Contributor
from app.models.base import utcnow


def contributor_key(installation_id: str, settings: Settings) -> str:
    """HMAC of the installation ID: stable per installation, but the raw ID is never stored."""
    return hmac.new(settings.contributor_id_salt.encode(), installation_id.encode(), hashlib.sha256).hexdigest()


def get_or_create_contributor(db: Session, installation_id: str, settings: Settings, *, synthetic: bool) -> Contributor:
    key = contributor_key(installation_id, settings)
    contributor = db.scalar(select(Contributor).where(Contributor.contributor_key == key))
    if contributor is None:
        contributor = Contributor(contributor_key=key, is_synthetic=synthetic)
        db.add(contributor)
        db.flush()
    contributor.last_seen_at = utcnow()
    return contributor
