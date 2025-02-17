import logging
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from sbmod.constants import BOT
from sbmod.utilities import add_contributor, seconds_to_next_hour
from tests.test_sbmod import create_mock_redditor


def test_add_contributor__no_conversation(caplog: pytest.LogCaptureFixture) -> None:
    mock_subreddit = Mock(**{"modmail.conversations.return_value": []})
    with caplog.at_level(logging.INFO):
        assert add_contributor(redditor=create_mock_redditor(), report="some report", subreddit=mock_subreddit)
    assert len(caplog.records) == 1
    assert caplog.records[0].message == "Failed to locate add contributor message for redditor:\nsome report"


def test_add_contributor__replies_once() -> None:
    mock_conversation = Mock(authors=[redditor := create_mock_redditor(), BOT], num_messages=1)
    mock_subreddit = Mock()
    mock_subreddit.modmail.conversations.return_value = [mock_conversation, mock_conversation]
    assert add_contributor(redditor=redditor, report="some report", subreddit=mock_subreddit)
    mock_conversation.reply.assert_called_once_with(body="some report", internal=True)


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
