import pytest
import sqlalchemy

from sbmod.models import AddContributorTask, Base, db_session


def test_add_contributor_task__duplicate_username() -> None:
    with pytest.raises(sqlalchemy.exc.IntegrityError), db_session(engine_url="sqlite:///:memory:") as session:  # noqa: PT012
        Base.metadata.create_all(session.get_bind())
        session.add(AddContributorTask(report="Some report", username="user1"))
        session.add(AddContributorTask(report="Some report", username="user1"))
        session.flush()


def test_add_contributor_task__next_task() -> None:
    with db_session(engine_url="sqlite:///:memory:") as session:
        Base.metadata.create_all(session.get_bind())
        session.add(task := AddContributorTask(report="Some report", username="user1"))
        session.flush()

        assert AddContributorTask.next_task(session=session) == task
        assert AddContributorTask.next_task(session=session) == task


def test_add_contributor_task__next_task__empty_table() -> None:
    with db_session(engine_url="sqlite:///:memory:") as session:
        Base.metadata.create_all(session.get_bind())
        assert AddContributorTask.next_task(session=session) is None
