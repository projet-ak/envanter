"""İlk kurulumda varsayılan durum etiketlerini ekler."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models

DEFAULT_STATUSES = [
    ("Kullanıma Hazır", models.StatusType.deployable),
    ("Beklemede", models.StatusType.pending),
    ("Arşiv", models.StatusType.archived),
    ("Arızalı", models.StatusType.undeployable),
]


def seed_defaults(db: Session) -> None:
    if db.scalar(select(models.StatusLabel).limit(1)) is None:
        for name, status_type in DEFAULT_STATUSES:
            db.add(models.StatusLabel(name=name, type=status_type))
        db.commit()
