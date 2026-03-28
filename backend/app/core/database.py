import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=settings.debug,
)


@event.listens_for(engine, "checkout")
def _on_checkout(dbapi_conn, connection_rec, connection_proxy):
    pool = engine.pool
    checked_out = pool.checkedout()
    max_total = pool.size() + pool._max_overflow
    if checked_out >= max_total - 2:
        logger.warning(
            "DB pool nearly exhausted: %d/%d connections checked out",
            checked_out,
            max_total,
        )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
