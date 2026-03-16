from collections.abc import Generator
import os
from pathlib import Path
import shutil
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import AnalysisResultModel, AnalysisRunModel, ImportRunModel, SourceModel


@pytest.fixture
def session() -> Generator[Session, None, None]:
    base_dir = Path.cwd() / ".tmp_testdata"
    base_dir.mkdir(parents=True, exist_ok=True)
    fd, raw_path = tempfile.mkstemp(dir=base_dir, suffix=".sqlite3")
    os.close(fd)
    db_file = Path(raw_path)
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        db_file.unlink(missing_ok=True)


@pytest.fixture
def workspace_tmp_path() -> Generator[Path, None, None]:
    base_dir = Path.cwd() / ".tmp_testdata"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=base_dir))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
