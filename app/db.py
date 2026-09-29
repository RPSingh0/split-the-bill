from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

PLAIN_SCHEME = "postgresql://"
PSYCOPG_SCHEME = "postgresql+psycopg://"


def engine_url(url):
    if url.startswith(PLAIN_SCHEME):
        return PSYCOPG_SCHEME + url.removeprefix(PLAIN_SCHEME)

    return url


engine = create_engine(engine_url(settings.database_url), pool_pre_ping=True, pool_size=5)
SessionLocal = sessionmaker(engine)


def get_db():
    with SessionLocal() as session:
        yield session
