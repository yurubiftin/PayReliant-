"""The connection between the app and PostgreSQL.

- engine:       the actual connection to the database
- SessionLocal: makes a "session" — one conversation with the database
- Base:         every table class in models.py inherits from this
- get_db:       gives each API request its own session, then closes it
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
