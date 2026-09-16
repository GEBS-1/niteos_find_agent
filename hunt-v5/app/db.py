from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def _engine_url() -> str:
    url = settings.database_url
    if url.startswith("sqlite:///./"):
        rel = url.removeprefix("sqlite:///./")
        return f"sqlite:///{(DATA_DIR.parent / rel).resolve().as_posix()}"
    if url.startswith("sqlite:///"):
        # absolute already or relative without ./
        path = url.removeprefix("sqlite:///")
        if not Path(path).is_absolute():
            return f"sqlite:///{(ROOT / path).resolve().as_posix()}"
    return url

if settings.database_url.startswith("sqlite"):
    engine = create_engine(_engine_url(), connect_args={"check_same_thread": False})
else:
    engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
