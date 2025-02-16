"""Provides functions for processing user-triggered input."""

import logging
import pprint
import time
import traceback
from typing import cast

from praw import Reddit
from praw.models import Message, Redditor
from prawcore.exceptions import PrawcoreException

from sbmod.constants import EXCEPTION_SLEEP_TIME, EXCEPTION_USER, SUBREDDIT, USER_AGENT
from sbmod.utilities import process_redditor

log = logging.getLogger(__package__)


class Bot:
    """Bot that encompasses most of the work."""

    @property
    def moderators(self) -> list[Redditor]:
        """Return list of Redditors who are moderators."""
        if self._moderators is None:
            self._moderators = list(self.subreddit.moderator())
        return self._moderators

    def __init__(self) -> None:
        """Initialize variables needed throughout the various Bot actions."""
        self._moderators = None
        self._running = True
        self.reddit = Reddit("sbmod", user_agent=USER_AGENT)
        self._exception_user = self.reddit.redditor(EXCEPTION_USER)
        self.subreddit = self.reddit.subreddit(SUBREDDIT)

    def _run_loop(self) -> None:
        """Loop through actions, either queued, or user-input."""
        log.info("Waiting for inbox messages")

        for item in self.reddit.inbox.stream(pause_after=4):
            if item is None:
                self.handle_queued_task()
                continue

            if item.was_comment:  # ignore comments
                item.mark_read()
                continue

            try:
                self.handle_message(message=cast(Message, item))
            except Exception:
                item_info = pprint.pformat(vars(item), indent=4)
                log.exception("Exception processing the following item:\n%s", item_info)

                message = f"Exception\n{traceback.format_exc()}\nItem:\n{item_info}".replace("\n", "\n\n")
                self._exception_user.message(message=message, subject=f"{USER_AGENT} exception")
                time.sleep(EXCEPTION_SLEEP_TIME)  # Let's slow things down if there are issues
                continue
            item.mark_read()

    def handle_message(self, *, message: Message) -> None:
        """Process a single inbox message."""
        if message.author not in self.moderators:
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
        process_redditor(redditor=self.reddit.redditor(body), subreddit=self.subreddit)

    def handle_queued_task(self) -> None:
        """Run a single queued task if one exists."""
        log.info("There are no queued tasks.")

    def run(self) -> None:
        """Provide the primary bot loop."""
        while self._running:
            try:
                self._run_loop()
            except KeyboardInterrupt:
                self._running = False
            except PrawcoreException:
                log.exception("PrawcoreException in run. Sleeping for %d seconds.", EXCEPTION_SLEEP_TIME)
                time.sleep(EXCEPTION_SLEEP_TIME)
        log.info("%s stopped gracefully", USER_AGENT)
