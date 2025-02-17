"""Define models that are backed by sqlite."""

import datetime
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Self

from sqlalchemy import TIMESTAMP, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.sql import func

from sbmod.constants import DB_PATH

timestamp = Annotated[
    datetime.datetime, mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.CURRENT_TIMESTAMP())
]


class Base(DeclarativeBase):
    """Base SQL model."""


class AddContributorTask(Base):
    """Represent work that should be done."""

    __tablename__ = "add_contributor_tasks"
    created_at: Mapped[timestamp]
    report: Mapped[str]
    username: Mapped[str] = mapped_column(primary_key=True)

    @classmethod
    def next_task(cls, *, session: Session) -> Self | None:
        """Return a single task if one exists."""
        return session.query(cls).first()


@contextmanager
def db_session(engine_url: str = f"sqlite:///{DB_PATH}") -> Iterator[Session]:
    """Provide access to the sqlite database."""
    engine = create_engine(engine_url)
    session = Session(engine, autobegin=False)
    try:
        session.begin()
        try:
            yield session
        except:
            session.rollback()
            raise
        else:
            session.commit()
    finally:
        session.close()
