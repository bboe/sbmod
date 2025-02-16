"""Moderation tool to help moderate r/SantaBarbara."""

import argparse
import logging
import pprint
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta
from typing import TextIO, cast
from zoneinfo import ZoneInfo

import prawcore
from praw import Reddit
from praw.models import Comment, Message, Redditor, Subreddit

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT = "sbmodbot"
EXCEPTION_SLEEP_TIME = 60
EXCEPTION_USER = "bboe"
FAILED_VERIFICATION_CONVERSATION_ID = "2i4snm"
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


def handle_message(*, message: Message, moderators: list[Redditor], reddit: Reddit, subreddit: Subreddit) -> None:
    """Process a single inbox message."""
    if message.author not in moderators:
        log.info("ignoring message from non-moderator user %s", message.author)
        return

    subject = message.subject.strip()
    if subject != "verify":
        message.reply(f"`{subject}` is not a valid command. Try `verify`.")
        return

    body = message.body.strip()
    if len(body.split()) != 1:
        message.reply("Message body must contain only a username")

    for prefix in ("u/", "/u/"):
        if body.lower().startswith(prefix):
            body = body[len(prefix) :]

    message.reply(f"processing {body} ...")
    process_redditor(redditor=reddit.redditor(body), subreddit=subreddit)


def handle_messages(*, reddit: Reddit, subreddit: Subreddit) -> None:
    """Loop through all mod-specific conversations for actions."""
    moderators = list(subreddit.moderator())

    for item in reddit.inbox.stream():
        if item.was_comment:  # ignore comments
            item.mark_read()
            continue

        try:
            handle_message(message=cast(Message, item), moderators=moderators, reddit=reddit, subreddit=subreddit)
        except Exception:
            item_info = pprint.pformat(vars(item), indent=4)
            log.exception("Exception processing the following item:\n%s", item_info)

            message = f"Exception\n{traceback.format_exc()}\nItem:\n{item_info}".replace("\n", "\n\n")
            reddit.redditor(EXCEPTION_USER).message(message=message, subject=f"{USER_AGENT} exception")
            time.sleep(EXCEPTION_SLEEP_TIME)  # Let's slow things down if there are issues
            continue
        item.mark_read()


def list_active_redditors(subreddit: Subreddit) -> None:
    """Output a list of the redditors who have commented in the most recent 1000 submissions."""
    redditors = Counter()
    log.info("fetching submissions")
    submissions = list(subreddit.new(limit=None))
    log.info("found %d submissions", len(submissions))
    for submission in submissions:
        submission.comments.replace_more(limit=0)
        comments = submission.comments.list()
        log.info("found %d comments", len(comments))
        for comment in comments:
            redditors[comment.author] += 1
    print(redditors.most_common(None))


def main() -> int:
    """Entrypoint to the program."""
    reddit = Reddit("sbmod", user_agent=USER_AGENT)
    subreddit = reddit.subreddit(SUBREDDIT)

    parser = argparse.ArgumentParser()
    parser.add_argument("--active", action="store_true", help="Obtain list of recently active users")
    parser.add_argument("--from-list", action="store_true", help="Add contributors from stdin")
    parser.add_argument("--run", action="store_true", help="Monitor messages for requests")
    parser.add_argument("--verify", metavar="redditor", help="Verify a single user")
    arguments = parser.parse_args()

    if arguments.active:
        list_active_redditors(subreddit=subreddit)
        return 0

    if arguments.from_list:
        process_redditors_from_list(fp=sys.stdin, reddit=reddit, subreddit=subreddit)
        return 0

    if arguments.verify:
        result, report = process_redditor(redditor=reddit.redditor(arguments.verify), subreddit=subreddit)
        print(report)
        return 0 if result else 1

    if arguments.run:
        run(reddit=reddit, subreddit=subreddit)
    return 0


def process_redditor(*, redditor: Redditor, subreddit: Subreddit) -> tuple[bool, str]:
    """Run the verification for a single Redditor."""
    verification = Verification(redditor=redditor, subreddit=subreddit)
    result = verification.verify()
    report = verification.report()
    if result:
        subreddit.contributor.add(redditor)
        for conversation in subreddit.modmail.conversations(state="all", limit=None):
            if redditor in conversation.authors and BOT in conversation.authors and conversation.num_messages == 1:
                conversation.reply(body=report, internal=True)
    else:
        subreddit.modmail(FAILED_VERIFICATION_CONVERSATION_ID).reply(body=report)
    return result, report


def process_redditors_from_list(*, fp: TextIO, reddit: Reddit, subreddit: Subreddit) -> None:
    """Add all redditors from list provided via fp."""
    contributors = set(subreddit.contributor(limit=None))
    log.info("Found %d contributors", len(contributors))
    for line in fp.readlines():
        username = line.strip()
        if not username:
            continue
        redditor = reddit.redditor(username)
        if redditor in contributors:
            log.info("Already a contributor: %s", redditor)
            continue

        process_redditor(redditor=redditor, subreddit=subreddit)


def run(*, reddit: Reddit, subreddit: Subreddit) -> None:
    """Primary loop when started with --run."""
    running = True
    while running:
        try:
            handle_messages(reddit=reddit, subreddit=subreddit)
        except KeyboardInterrupt:
            running = False
        except prawcore.exceptions.PrawcoreException:
            log.exception("PrawcoreException in run. Sleeping for %d seconds.", EXCEPTION_SLEEP_TIME)
            time.sleep(EXCEPTION_SLEEP_TIME)
    log.info("%s stopped gracefully", USER_AGENT)


if __name__ == "__main__":
    sys.exit(main())
