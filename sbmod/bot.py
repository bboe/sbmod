"""Provides functions for processing user-triggered input."""

import logging
import pprint
import time
import traceback
from typing import cast

from praw import Reddit
from praw.models import Message, Redditor, Subreddit

from sbmod.constants import EXCEPTION_SLEEP_TIME, EXCEPTION_USER, USER_AGENT
from sbmod.utilities import process_redditor

log = logging.getLogger(__name__)


def handle_message(*, message: Message, moderators: list[Redditor], reddit: Reddit, subreddit: Subreddit) -> None:
    """Process a single inbox message."""
    if message.author not in moderators:
        log.info("ignoring message from non-moderator user %s", message.author)
        return

    subject = message.subject.strip()
    if subject != "verify":
        log.info("invalid subject %r from %s", subject, message.author)
        message.reply(f"`{subject}` is not a valid command. Try `verify`.")
        return

    body = message.body.strip()
    if len(body.split()) != 1:
        log.info("invalid body %r from %s", body, message.author)
        message.reply("Message body must contain only a username")
        return

    for prefix in ("u/", "/u/"):
        if body.lower().startswith(prefix):
            body = body[len(prefix) :]

    log.info("processing %s ...", body)
    message.reply(f"processing {body} ...")
    process_redditor(redditor=reddit.redditor(body), subreddit=subreddit)


def handle_messages(*, reddit: Reddit, subreddit: Subreddit) -> None:
    """Loop through all mod-specific conversations for actions."""
    moderators = list(subreddit.moderator())
    log.info("Waiting for inbox messages")

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
