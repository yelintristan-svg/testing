"""Runtime settings, read from environment variables.

Nothing here holds a real credential. Secrets (ANTHROPIC_API_KEY, Calendly
signing key, SMTP password) are only ever read from the environment.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: Path(_env("CRM_DB", "crm.sqlite3")))
    outbox_dir: Path = field(default_factory=lambda: Path(_env("CRM_OUTBOX", "outbox")))

    # "dryrun" writes .eml files to the outbox. "smtp" is wired but refuses to
    # run unless CRM_ALLOW_LIVE_SEND=true, so nothing goes out by accident.
    mailer: str = field(default_factory=lambda: _env("CRM_MAILER", "dryrun"))
    allow_live_send: bool = field(default_factory=lambda: _env_bool("CRM_ALLOW_LIVE_SEND", False))

    # Claude. "offline" uses a deterministic template so the engine runs
    # without an API key (tests, demos).
    llm: str = field(default_factory=lambda: _env("CRM_LLM", "offline"))
    model: str = field(default_factory=lambda: _env("CRM_MODEL", "claude-opus-5-5"))
    effort: str = field(default_factory=lambda: _env("CRM_EFFORT", "medium"))

    # Every first-touch draft waits for a human "approve" unless switched off.
    require_review: bool = field(default_factory=lambda: _env_bool("CRM_REQUIRE_REVIEW", True))

    # Throttling, per sending mailbox.
    daily_cap: int = field(default_factory=lambda: _env_int("CRM_DAILY_CAP", 40))
    hourly_cap: int = field(default_factory=lambda: _env_int("CRM_HOURLY_CAP", 12))
    min_gap_seconds: int = field(default_factory=lambda: _env_int("CRM_MIN_GAP_SECONDS", 90))
    warmup_days: int = field(default_factory=lambda: _env_int("CRM_WARMUP_DAYS", 28))
    warmup_start_cap: int = field(default_factory=lambda: _env_int("CRM_WARMUP_START_CAP", 10))
    send_window_start: int = field(default_factory=lambda: _env_int("CRM_SEND_START_HOUR", 8))
    send_window_end: int = field(default_factory=lambda: _env_int("CRM_SEND_END_HOUR", 18))
    timezone: str = field(default_factory=lambda: _env("CRM_TZ", "Europe/London"))

    # Compliance.
    unsubscribe_secret: str = field(default_factory=lambda: _env("CRM_UNSUB_SECRET", "dev-only-change-me"))
    public_base_url: str = field(default_factory=lambda: _env("CRM_PUBLIC_URL", "http://localhost:8080"))
    # 'link' (needs `crm serve` hosted at CRM_PUBLIC_URL) or 'reply' (lean launch).
    unsub_mode: str = field(default_factory=lambda: _env("CRM_UNSUB_MODE", "link"))
    retention_days: int = field(default_factory=lambda: _env_int("CRM_RETENTION_DAYS", 365))

    # People (is_ai=0 senders) send from the daily list by hand rather than via the mailer.
    hand_send: bool = field(default_factory=lambda: _env_bool("CRM_HAND_SEND", True))

    # Daily list (crm daily). 20 hand-sent emails a day is the lean-launch pace.
    daily_emails: int = field(default_factory=lambda: _env_int("CRM_DAILY_EMAILS", 20))
    # Email lookup: 'none' (default, no network), 'apollo' or 'hunter'. Keys from the environment only.
    email_provider: str = field(default_factory=lambda: _env("CRM_EMAIL_PROVIDER", "none"))
    apollo_api_key: str = field(default_factory=lambda: _env("APOLLO_API_KEY", ""))
    hunter_api_key: str = field(default_factory=lambda: _env("HUNTER_API_KEY", ""))
    # Lookups cost credits; cap them per run.
    daily_lookups: int = field(default_factory=lambda: _env_int("CRM_DAILY_LOOKUPS", 30))

    # LinkedIn invitations Tristan sends by hand. LinkedIn caps invitations at
    # roughly 100 a week, and free accounts get only a few personalised notes a
    # month, so notes are kept short (200 characters) and used for the best fits.
    linkedin_daily: int = field(default_factory=lambda: _env_int("CRM_LINKEDIN_DAILY", 20))
    linkedin_weekly: int = field(default_factory=lambda: _env_int("CRM_LINKEDIN_WEEKLY", 80))
    linkedin_note_chars: int = field(default_factory=lambda: _env_int("CRM_LINKEDIN_NOTE_CHARS", 200))

    # Booking.
    calendly_signing_key: str = field(default_factory=lambda: _env("CALENDLY_WEBHOOK_SIGNING_KEY", ""))
    recruiter_name: str = field(default_factory=lambda: _env("CRM_RECRUITER_NAME", "Tristan"))
    recruiter_title: str = field(default_factory=lambda: _env("CRM_RECRUITER_TITLE", "Head of Recruitment"))
    recruiter_email: str = field(default_factory=lambda: _env("CRM_RECRUITER_EMAIL", "tristan@example.com"))


def load() -> Settings:
    return Settings()
