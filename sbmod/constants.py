"""Provide constants for the package."""

from pathlib import Path
from zoneinfo import ZoneInfo

BOT = "sbmodbot"
DB_PATH = Path.home() / ".config" / "sbmod.db"
EXCEPTION_SLEEP_TIME = 60
EXCEPTION_USER = "bboe"
FAILED_VERIFICATION_CONVERSATION_ID = "2i4snm"
SUBREDDIT = "santabarbara"
SUBREDDITS_TO_SHOW = 10
TIMEZONE = ZoneInfo("America/Los_Angeles")
USER_AGENT = "SBModTool by u/bboe v0.1.0"
VERSION = "0.1.0"
