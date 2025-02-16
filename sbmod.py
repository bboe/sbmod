"""Moderation tool to help moderate r/SantaBarbara."""

import argparse
import logging
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import prawcore
from praw import Reddit
from praw.models import Comment, Redditor, Subreddit

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT = "sbmodbot"
SUBREDDIT = "santabarbara"
SUBREDDITS_TO_SHOW = 10
TIMEZONE = ZoneInfo("America/Los_Angeles")
USER_AGENT = "SBModTool by u/bboe v0.1.0"

DATES = {
    "created": datetime.now(tz=TIMEZONE) - timedelta(days=14),
    "history": datetime(year=2024, month=11, day=5, tzinfo=TIMEZONE),
    "positive_karma": datetime(year=2025, month=1, day=20, tzinfo=TIMEZONE),
}


def _d(timestamp: float, /) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=TIMEZONE)


class Verification:
    """Analyze and provide report on a redditor's activity history."""

    def __init__(self, *, redditor: Redditor, subreddit: Subreddit) -> None:
        """Store information about this particular Verification."""
        self._redditor = redditor
        self._subreddit = subreddit
        self._verified: bool | None = None
        self.comments: list[Comment] = []
        self.error: str | None = None
        self.found_comments = 0
        self.karma: int | None = None
        self.karma_average: float | None = None
        self.note_types = Counter()
        self.subreddits: Counter[Subreddit] = Counter()

    @property
    def created(self) -> datetime:
        """Return the datetime the ``Redditor`` was created."""
        return _d(self._redditor.created_utc)

    def _process_comments(self) -> bool:
        """Fetch as many comments for the redditor and save some information."""
        log.info("fetching comments for %s", self._redditor)
        for comment in self._redditor.comments.new(limit=1000):
            self.found_comments += 1
            self.subreddits[comment.subreddit] += 1
            if comment.subreddit != self._subreddit:
                continue
            self.comments.append(comment)
        self.comments.sort(key=lambda x: x.created_utc)

        if not self.comments:
            self.error = f"has no r/{self._subreddit} history."
            return False

        oldest_comment_date = _d(self.comments[0].created_utc)
        if oldest_comment_date > DATES["positive_karma"]:
            self.error = f"oldest r/{self._subreddit} comment is too recent ({oldest_comment_date})"
            return False

        self.karma = sum(comment.score for comment in self.comments)
        self.karma_average = self.karma / len(self.comments)

        if oldest_comment_date > DATES["history"] and self.karma_average < 1:
            self.error = "too low of karma average"
            return False
        return True

    def _process_notes(self) -> bool:
        """Collect counts of mod notes. Return true if validation should continue."""
        for note in self._subreddit.mod.notes.redditors(self._redditor, limit=None):
            self.note_types[note.type] += 1
        if (bans := self.note_types["BAN"]) > 0:
            self.error = f"has {bans} ban(s). Skipped history collection."
            return False
        if (mutes := self.note_types["MUTE"]) > 0:
            self.error = f"has {mutes} mute(s). Skipped history collection."
            return False
        return True

    def _redditor_status(self) -> None:
        try:
            self._redditor.is_blocked  # noqa: B018
        except prawcore.exceptions.NotFound:
            self.error = "is not found. No history information available."
            return

        if getattr(self._redditor, "is_suspended", False):
            self.error = "is suspended. No history information available."
            return

        if self.created > DATES["created"]:
            self.error = f"was created too recently ({self.created}). Skipped history collection."
            return

    def report(self) -> str:
        """Return a report that is reddit markdown formatted."""
        if self._verified is None:
            message = "verify hasn't been called yet"
            raise TypeError(message)
        if self._verified:
            return self.results()
        return f"u/{self._redditor.name}: verification fail\n\nAccount {self.error}"

    def results(self) -> str:
        """Return a reddit markdown report for the verification."""
        lines = []
        lines.append(f"                User: {self._redditor.name}")
        lines.append(f"             Created: {self.created}")
        lines.append(f"Commented subreddits: {len(self.subreddits)}")

        if len(self.subreddits) > SUBREDDITS_TO_SHOW:
            top_subreddits = self.subreddits.most_common(SUBREDDITS_TO_SHOW)
            lines.append(f"   Top {SUBREDDITS_TO_SHOW} subreddits:")
        else:
            top_subreddits = self.subreddits.most_common(None)
        for subreddit, count in top_subreddits:
            lines.append(f"                      - {subreddit} ({count} comments)")

        lines.append(f"Total comments found: {self.found_comments}")
        lines.append("")
        lines.append(f"r/{self._subreddit} specific")
        lines.append(f"            Comments: {len(self.comments)}")

        if self.comments:
            lines.append(f"       Comment karma: {self.karma}")
            lines.append(f"       Average karma: {self.karma_average:.02f}")
            lines.append(f"      Newest comment: {_d(self.comments[-1].created_utc)}")
            lines.append(f"      Oldest comment: {_d(self.comments[0].created_utc)}")

        for note_type, count in sorted(self.note_types.items()):
            lines.append(f"{note_type:>14} count: {count}")
        return "\n".join(f"    {line}" if line else "" for line in lines)

    def verify(self) -> bool:
        """Validate the redditor."""
        self._redditor_status()
        if self.error is not None or not self._process_notes():
            self._verified = False
        else:
            self._verified = self._process_comments()
        return self._verified


def handle_modmail(*, reddit: Reddit, subreddit: Subreddit) -> None:
    """Loop through all mod-specific conversations for actions."""
    for conversation in subreddit.modmail.conversations(state="mod", limit=None):
        if conversation.subject != "verify" or BOT in conversation.authors:
            continue

        assert conversation.is_internal, "is not internal"
        assert conversation.state in (0, 1), f"state is not in (0, 1) {conversation.state}"

        message = conversation.messages[0]
        username = message.body_markdown
        redditor = reddit.redditor(username)
        verification = Verification(redditor=redditor, subreddit=subreddit)
        verification.verify()
        report = verification.report()
        conversation.reply(body=report)


def main() -> int:
    """Entrypoint to the program."""
    reddit = Reddit("sbmod", user_agent=USER_AGENT)
    subreddit = reddit.subreddit(SUBREDDIT)

    parser = argparse.ArgumentParser()
    parser.add_argument("--report", metavar="redditor", help="Run report against a single user")
    parser.add_argument("--watch", action="store_true", help="Monitor modmail for requests")
    arguments = parser.parse_args()

    if arguments.report:
        redditor = reddit.redditor(arguments.report)
        verification = Verification(redditor=redditor, subreddit=subreddit)
        result = verification.verify()
        print(report := verification.report())
        if result:
            subreddit.contributor.add(redditor)
            for conversation in subreddit.modmail.conversations(state="all", limit=None):
                if redditor in conversation.authors and BOT in conversation.authors and conversation.num_messages == 1:
                    conversation.reply(body=report, internal=True)
        return 0 if result else 1

    if arguments.watch:
        while True:
            try:
                handle_modmail(reddit=reddit, subreddit=subreddit)
            except Exception:
                log.exception("handle modmail failed")
            time.sleep(60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
