"""Provides functions that facilitate actions."""

import json
from pathlib import Path

from praw.exceptions import RedditAPIException
from praw.models import Redditor, Subreddit

from sbmod.constants import BOT, FAILED_VERIFICATION_CONVERSATION_ID
from sbmod.verification import Verification


def process_redditor(*, redditor: Redditor, subreddit: Subreddit) -> tuple[bool, str]:
    """Run the verification for a single Redditor."""
    verification = Verification(redditor=redditor, subreddit=subreddit)
    result = verification.verify()
    report = verification.report()
    if result:
        try:
            subreddit.contributor.add(redditor)
        except RedditAPIException as exception:
            if exception.items[0].error_type == "SUBREDDIT_RATELIMIT":
                data = {"contributor": str(redditor), "report": report}
                with Path(f"contributor_{redditor}.json").open("w") as fp:
                    json.dump(data, fp)
                return result, report
        for conversation in subreddit.modmail.conversations(state="all", limit=None):
            if redditor in conversation.authors and BOT in conversation.authors and conversation.num_messages == 1:
                conversation.reply(body=report, internal=True)
                break
    else:
        subreddit.modmail(FAILED_VERIFICATION_CONVERSATION_ID).reply(body=report)
    return result, report
