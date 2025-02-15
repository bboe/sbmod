"""Moderation tool to help moderate r/SantaBarbara."""

import logging
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import praw
import prawcore

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

BOT = "sbmodbot"
SUBREDDIT = "santabarbara"
TIMEZONE = ZoneInfo("America/Los_Angeles")


def _d(timestamp: float, /) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=TIMEZONE)


class Verification:
    """Analyze and provide report on a redditor's activity history."""

    def __init__(self, redditor: praw.models.Redditor, /) -> None:
        """Store information about this particular Verification."""
        self._redditor = redditor
        self.comments: list[praw.models.Comment] = []
        self.error: str
        self.found_comments = 0
        self.subreddits: set[praw.models.Subreddits] = set()

    @property
    def created(self) -> datetime:
        """Return the datetime the ``Redditor`` was created."""
        return _d(self._redditor.created_utc)

    def _process_comments(self) -> None:
        """Fetch as many comments for the redditor and save some information."""
        log.info("fetching comments for %s", self._redditor)
        for comment in self._redditor.comments.new(limit=None):
            self.found_comments += 1
            if comment.subreddit != SUBREDDIT:
                self.subreddits.add(comment.subreddit)
                continue
            self.comments.append(comment)
        self.comments.sort(key=lambda x: x.created_utc)

    def process(self) -> bool:
        """Validate the redditor."""
        try:
            if self._redditor.is_suspended:
                self.error = "is suspended"
                return False
        except prawcore.exceptions.NotFound:
            self.error = "is not found"
            return False
        self._process_comments()
        return True

    def results(self) -> str:
        """Return a reddit markdown report for the verification."""
        karma = sum(comment.score for comment in self.comments)
        average_karma = karma / len(self.comments)
        lines = []
        lines.append(f"                User: {self._redditor}")
        lines.append(f"             Created: {self.created}")
        lines.append(f"Commented subreddits: {len(self.subreddits)}")
        lines.append(f"Total comments found: {self.found_comments}")
        lines.append("")
        lines.append(f"{SUBREDDIT} specific")
        lines.append(f"            Comments: {len(self.comments)}")
        lines.append(f"       Comment karma: {karma}")
        lines.append(f"       Average karma: {average_karma:.02f}")
        lines.append(f"      Newest comment: {_d(self.comments[-1].created_utc)}")
        lines.append(f"      Oldest comment: {_d(self.comments[0].created_utc)}")
        return "\n".join(f"    {line}" for line in lines)


def handle_modmail(*, reddit: praw.Reddit) -> None:
    """Loop through all mod-specific conversations for actions."""
    subreddit = reddit.subreddit(SUBREDDIT)

    for conversation in subreddit.modmail.conversations(state="mod", limit=None):
        if conversation.subject != "verify" or BOT in conversation.authors:
            continue

        assert conversation.is_internal, "is not internal"
        assert conversation.state in (0, 1), f"state is not in (0, 1) {conversation.state}"

        message = conversation.messages[0]
        username = message.body_markdown
        redditor = reddit.redditor(username)
        verification = Verification(redditor)
        if verification.process():
            conversation.reply(body=verification.results())
        else:
            conversation.reply(body=f"u/{redditor.name} {verification.error}. No history information available.")


def main() -> int:
    """Entrypoint to the program."""
    reddit = praw.Reddit("sbmod", user_agent="SBModTool by u/bboe v0.0.1")

    while True:
        try:
            handle_modmail(reddit=reddit)
        except Exception:
            log.exception("handle modmail failed")
        time.sleep(60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
