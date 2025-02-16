"""Provide the command line entry point into the package."""

import argparse
import logging
import sys
import time
from collections import Counter
from typing import TextIO

from praw import Reddit
from praw.models import Subreddit
from prawcore.exceptions import PrawcoreException

from sbmod.bot import handle_messages
from sbmod.constants import EXCEPTION_SLEEP_TIME, SUBREDDIT, USER_AGENT
from sbmod.utilities import process_redditor

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__package__)


def list_active_redditors(subreddit: Subreddit) -> None:
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


def main() -> int:
    """Entrypoint to the program."""
    reddit = Reddit("sbmod", user_agent=USER_AGENT)
    subreddit = reddit.subreddit(SUBREDDIT)

    parser = argparse.ArgumentParser()
    parser.add_argument("--active", action="store_true", help="Obtain list of recently active users")
    parser.add_argument("--from-list", action="store_true", help="Add contributors from stdin")
    parser.add_argument("--verify", metavar="redditor", help="Verify a single user")
    arguments = parser.parse_args()

    if arguments.active:
        list_active_redditors(subreddit=subreddit)
        return 0

    if arguments.verify:
        result, report = process_redditor(redditor=reddit.redditor(arguments.verify), subreddit=subreddit)
        print(report)
        return 0 if result else 1

    if arguments.from_list:
        process_redditors_from_list(fp=sys.stdin, reddit=reddit, subreddit=subreddit)

    run(reddit=reddit, subreddit=subreddit)
    return 0


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
        except PrawcoreException:
            log.exception("PrawcoreException in run. Sleeping for %d seconds.", EXCEPTION_SLEEP_TIME)
            time.sleep(EXCEPTION_SLEEP_TIME)
    log.info("%s stopped gracefully", USER_AGENT)


if __name__ == "__main__":
    sys.exit(main())
