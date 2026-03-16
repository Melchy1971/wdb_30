"""
FastAPI Dependency Injection.
Zentraler Einstiegspunkt für alle wiederverwendbaren Abhängigkeiten.
"""
from collections.abc import Generator
from sqlalchemy.orm import Session
from app.db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    DB-Session als FastAPI-Dependency.
    Öffnet eine Session pro Request und schließt sie sicher nach Abschluss.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
