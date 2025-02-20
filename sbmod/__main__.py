"""Provide the command line entry point into the package."""

import argparse
import logging
import sys

from sbmod.bot import Bot
from sbmod.utilities import (
    list_active_redditors,
    list_redditors_with_admin_removed_items,
    process_redditor,
    process_redditors_from_list,
)

log = logging.getLogger(__package__)


def setup_logging(*, debug: bool) -> None:
    """Prepare logging."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s", level=level)


def main() -> int:
    """Provide the entrypoint to the program."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--active", action="store_true", help="Obtain list of recently active users")
    parser.add_argument(
        "--admin", action="store_true", help="Obtain list of users who have had items removed by Reddit"
    )
    parser.add_argument("--contributors", action="store_true", help="Obtain list of users who are contributors")
    parser.add_argument("--debug", action="store_true", help="Turn on verbose logging")
    parser.add_argument("--from-list", action="store_true", help="Add contributors from stdin")
    parser.add_argument("--verify", metavar="redditor", help="Verify a single user")
    arguments = parser.parse_args()

    setup_logging(debug=arguments.debug)

    bot = Bot()

    if arguments.active:
        list_active_redditors(subreddit=bot.subreddit)
        return 0

    if arguments.admin:
        list_redditors_with_admin_removed_items(subreddit=bot.subreddit)
        return 0

    if arguments.contributors:
        for contributor in bot.contributors:
            print(contributor)
        return 0

    if arguments.verify:
        result, report = process_redditor(redditor=bot.reddit.redditor(arguments.verify), subreddit=bot.subreddit)
        print(report)
        return 0 if result else 1

    if arguments.from_list:
        process_redditors_from_list(fp=sys.stdin, reddit=bot.reddit, subreddit=bot.subreddit)

    bot.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
