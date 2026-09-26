from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config.settings import DB_PATH


class Base(DeclarativeBase):
    pass


engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db():
    from app.models import orm  # noqa: F401  (registers models)
    Base.metadata.create_all(engine)


def get_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
