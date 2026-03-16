from pathlib import Path

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.db import models  # noqa: F401


def init_db() -> None:
    settings = get_settings()
    db_path = Path(settings.sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
