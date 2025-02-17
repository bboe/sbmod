"""Provides functions that facilitate actions."""

import json
import logging
import math
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TextIO

from praw import Reddit
from praw.exceptions import RedditAPIException
from praw.models import Redditor, Subreddit

from sbmod.constants import BOT, FAILED_VERIFICATION_CONVERSATION_ID
from sbmod.models import AddContributorTask, db_session
from sbmod.verification import Verification

log = logging.getLogger(__package__)


def add_contributor(
    *, redditor: Redditor, report: str, save_to_db_on_failure: bool = True, subreddit: Subreddit
) -> bool:
    """Add a contributor to the subreddit."""
    try:
        subreddit.contributor.add(redditor)
    except RedditAPIException as exception:
        if exception.items[0].error_type == "SUBREDDIT_RATELIMIT":
            log.warning("add_contributor hit rate limit")
            if not save_to_db_on_failure:
                return False

            with db_session() as session:
                session.add(AddContributorTask(report=report, username=redditor.name))
            return False
        raise
    for conversation in subreddit.modmail.conversations(state="all", limit=None):
        if redditor in conversation.authors and BOT in conversation.authors and conversation.num_messages == 1:
            conversation.reply(body=report, internal=True)
            break
    else:
        log.warning("Failed to locate add contributor message for %s:\n%s", redditor.name, report)
    return True


def list_active_redditors(*, subreddit: Subreddit) -> None:
    """Output a list of the redditors who have commented in the most recent 1000 submissions."""
    redditors = Counter()
    log.info("fetching submissions")
    submissions = list(subreddit.new(limit=None))  # pyright: ignore[reportArgumentType]
    log.info("found %d submissions", len(submissions))
    for submission in submissions:
        submission.comments.replace_more(limit=0)
        comments = submission.comments.list()
        log.info("found %d comments", len(comments))
        for comment in comments:
            redditors[comment.author] += 1
    print(redditors.most_common(None))


def list_redditors_with_admin_removed_items(*, subreddit: Subreddit) -> None:
    """Output a list of redditors who have had submissions or comments removed by Reddit."""
    redditors = Counter()

    log.info("fetching anti-evil moderator log")
    for entry in subreddit.mod.log(limit=None, mod="a"):
        assert entry.action in ("removecomment", "removelink"), f"Unexpected entry action {entry.action}"
        redditors[entry.target_author] += 100

    log.info("fetching reddit moderator log")
    for entry in subreddit.mod.log(limit=None, mod="reddit"):
        if entry.action in ("addmoderator", "marknsfw", "unmuteuser"):  # Ignored actions
            continue
        assert entry.action in ("removecomment", "removelink"), f"Unexpected entry action {entry.action}"
        redditors[entry.target_author] += 1

    for redditor, count in sorted(redditors.items(), key=lambda x: (-x[1], x[0])):
        print(json.dumps({"count": count, "username": redditor}))


def process_redditor(*, redditor: Redditor, subreddit: Subreddit) -> tuple[bool, str]:
    """Run the verification for a single Redditor."""
    verification = Verification(redditor=redditor, subreddit=subreddit)
    result = verification.verify()
    report = verification.report()
    if result:
        add_contributor(redditor=redditor, report=report, subreddit=subreddit)
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


def seconds_to_next_hour() -> int:
    """Return the number of seconds to the next hour."""
    now = datetime.now(tz=UTC)
    next_hour = (now + timedelta(hours=1)).replace(microsecond=0, minute=0, second=0)
    return int(math.ceil((next_hour - now).total_seconds()))
