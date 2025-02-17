from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, PropertyMock, patch

from prawcore.exceptions import NotFound

from sbmod.constants import SUBREDDIT
from sbmod.utilities import seconds_to_next_hour
from sbmod.verification import DATES, Verification, _d


def create_mock_comment(*, created: float = 1700000000, score: int = 1, subreddit: Mock) -> Mock:
    """Return an object like praw.models.Comment."""
    comment = Mock()
    comment.created_utc = created
    comment.score = score
    comment.subreddit = subreddit
    return comment


def create_mock_note(*, type_: str = "BAN") -> Mock:
    """Return an object like praw.models.ModNote."""
    note = Mock()
    note.type = type_
    return note


def create_mock_redditor(
    *,
    comments: list[Mock] = None,
    created: float = DATES["created"].timestamp(),
    is_not_found: bool = False,
    is_suspended: bool = False,
    name: str = "redditor",
) -> Mock:
    """Return an object like praw.models.Redditor."""
    redditor = Mock()
    redditor.created_utc = created
    if is_not_found:
        type(redditor).is_blocked = PropertyMock(side_effect=NotFound(Mock()))
    redditor.is_suspended = is_suspended
    redditor.name = name
    redditor.comments.new = Mock(return_value=[] if comments is None else comments)
    return redditor


def create_mock_subreddit(*, name: str = SUBREDDIT, notes: list[Mock] = None) -> Mock:
    """Return an object like praw.models.Subreddit."""
    subreddit = MagicMock()
    subreddit.__str__.return_value = name  # pyright: ignore[reportFunctionMemberAccess]
    subreddit.mod.notes.redditors = Mock(return_value=[] if notes is None else notes)
    return subreddit


def test_seconds_to_next_hour() -> None:
    assert 0 < seconds_to_next_hour() <= 3600

    with patch("sbmod.utilities.datetime", now=(now_mock := Mock())):
        now_mock.return_value = datetime(day=1, month=1, tzinfo=UTC, year=2025)
        assert seconds_to_next_hour() == 3600

        now_mock.return_value = datetime(day=1, minute=59, month=1, tzinfo=UTC, year=2025)
        assert seconds_to_next_hour() == 60

        now_mock.return_value = datetime(day=1, minute=59, month=1, second=59, tzinfo=UTC, year=2025)
        assert seconds_to_next_hour() == 1

        now_mock.return_value = datetime(
            day=1, microsecond=999999, minute=59, month=1, second=59, tzinfo=UTC, year=2025
        )
        assert seconds_to_next_hour() == 1


def test_verification__is_not_found() -> None:
    mock_redditor = create_mock_redditor(is_not_found=True, name="notfound")
    mock_subreddit = create_mock_subreddit()
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert not verification.verify()
    assert (
        verification.report()
        == "u/notfound: verification fail\n\nAccount is not found. No history information available."
    )


def test_verification__is_suspended() -> None:
    mock_redditor = create_mock_redditor(is_suspended=True, name="suspended")
    mock_subreddit = create_mock_subreddit()
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert not verification.verify()
    assert (
        verification.report()
        == "u/suspended: verification fail\n\nAccount is suspended. No history information available."
    )


def test_verification__is_too_new() -> None:
    mock_redditor = create_mock_redditor(created=DATES["created"].timestamp() + 0.001, name="toonew")
    mock_subreddit = create_mock_subreddit()
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert not verification.verify()
    assert (
        verification.report()
        == f"u/toonew: verification fail\n\nAccount was created too recently ({_d(mock_redditor.created_utc)}). Skipped history collection."
    )


def test_verification__has_ban() -> None:
    mock_redditor = create_mock_redditor(name="hasban")
    mock_subreddit = create_mock_subreddit(notes=[create_mock_note()])
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert not verification.verify()
    assert verification.report() == "u/hasban: verification fail\n\nAccount has 1 ban(s). Skipped history collection."


def test_verification__has_bans() -> None:
    mock_redditor = create_mock_redditor(name="hasbans")
    mock_subreddit = create_mock_subreddit(notes=[create_mock_note(), create_mock_note()])
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert not verification.verify()
    assert verification.report() == "u/hasbans: verification fail\n\nAccount has 2 ban(s). Skipped history collection."


def test_verification__has_mutes() -> None:
    mock_redditor = create_mock_redditor(name="hasmutes")
    mock_subreddit = create_mock_subreddit(notes=[create_mock_note(type_="MUTE"), create_mock_note(type_="MUTE")])
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert not verification.verify()
    assert (
        verification.report() == "u/hasmutes: verification fail\n\nAccount has 2 mute(s). Skipped history collection."
    )


def test_verification__has_no_history() -> None:
    mock_redditor = create_mock_redditor(name="nohistory")
    mock_subreddit = create_mock_subreddit()
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert not verification.verify()
    assert verification.report() == "u/nohistory: verification fail\n\nAccount has no r/santabarbara history."


def test_verification__insufficient_karma__lower_bound() -> None:
    mock_subreddit = create_mock_subreddit()
    mock_redditor = create_mock_redditor(
        comments=[create_mock_comment(created=DATES["history"].timestamp() + 1, score=0, subreddit=mock_subreddit)]
    )
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert not verification.verify()
    assert verification.report() == "u/redditor: verification fail\n\nAccount too low of karma average"


def test_verification__insufficient_karma__upper_bound() -> None:
    mock_subreddit = create_mock_subreddit()
    mock_redditor = create_mock_redditor(
        comments=[create_mock_comment(created=DATES["positive_karma"].timestamp(), score=0, subreddit=mock_subreddit)]
    )
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert not verification.verify()
    assert verification.report() == "u/redditor: verification fail\n\nAccount too low of karma average"


def test_verification__oldest_comment_too_recent() -> None:
    mock_subreddit = create_mock_subreddit()
    mock_redditor = create_mock_redditor(
        comments=[create_mock_comment(created=DATES["positive_karma"].timestamp() + 1, subreddit=mock_subreddit)]
    )
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert not verification.verify()
    assert (
        verification.report()
        == "u/redditor: verification fail\n\nAccount oldest r/santabarbara comment is too recent (2025-01-20 00:00:01-08:00)"
    )


def test_verification__pass_with_low_karma() -> None:
    mock_subreddit = create_mock_subreddit()
    mock_redditor = create_mock_redditor(
        comments=[
            create_mock_comment(created=DATES["history"].timestamp(), score=0, subreddit=mock_subreddit),
            create_mock_comment(subreddit="a"),
        ]
    )
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert verification.verify()
    assert (
        verification.report()
        == f"""                    User: redditor
                 Created: {DATES["created"]}
    Commented subreddits: 2
                          - santabarbara (1 comments)
                          - a (1 comments)
    Total comments found: 2

    r/santabarbara specific
                Comments: 1
           Comment karma: 0
           Average karma: 0.00
          Newest comment: 2024-11-05 00:00:00-08:00
          Oldest comment: 2024-11-05 00:00:00-08:00"""
    )


def test_verification__pass_with_many_subreddits() -> None:
    mock_subreddit = create_mock_subreddit()
    mock_redditor = create_mock_redditor(
        comments=[
            create_mock_comment(created=DATES["history"].timestamp(), score=0, subreddit=mock_subreddit),
            create_mock_comment(subreddit="a"),
            create_mock_comment(subreddit="b"),
            create_mock_comment(subreddit="c"),
            create_mock_comment(subreddit="d"),
            create_mock_comment(subreddit="e"),
            create_mock_comment(subreddit="f"),
            create_mock_comment(subreddit="g"),
            create_mock_comment(subreddit="h"),
            create_mock_comment(subreddit="i"),
            create_mock_comment(subreddit="j"),
        ]
    )
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert verification.verify()
    assert (
        verification.report()
        == f"""                    User: redditor
                 Created: {DATES["created"]}
    Commented subreddits: 11
       Top 10 subreddits:
                          - santabarbara (1 comments)
                          - a (1 comments)
                          - b (1 comments)
                          - c (1 comments)
                          - d (1 comments)
                          - e (1 comments)
                          - f (1 comments)
                          - g (1 comments)
                          - h (1 comments)
                          - i (1 comments)
    Total comments found: 11

    r/santabarbara specific
                Comments: 1
           Comment karma: 0
           Average karma: 0.00
          Newest comment: 2024-11-05 00:00:00-08:00
          Oldest comment: 2024-11-05 00:00:00-08:00"""
    )


def test_verification__pass_with_mod_notes() -> None:
    mock_subreddit = create_mock_subreddit(
        notes=[
            create_mock_note(type_="APPROVAL"),
            create_mock_note(type_="APPROVAL"),
            create_mock_note(type_="REMOVAL"),
        ]
    )
    mock_redditor = create_mock_redditor(
        comments=[create_mock_comment(created=DATES["history"].timestamp(), score=0, subreddit=mock_subreddit)]
    )
    verification = Verification(redditor=mock_redditor, subreddit=mock_subreddit)
    assert verification.verify()
    assert (
        verification.report()
        == f"""                    User: redditor
                 Created: {DATES["created"]}
    Commented subreddits: 1
                          - santabarbara (1 comments)
    Total comments found: 1

    r/santabarbara specific
                Comments: 1
           Comment karma: 0
           Average karma: 0.00
          Newest comment: 2024-11-05 00:00:00-08:00
          Oldest comment: 2024-11-05 00:00:00-08:00
          APPROVAL count: 2
           REMOVAL count: 1"""
    )
