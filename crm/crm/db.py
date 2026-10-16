"""SQLite schema and connection helper.

SQLite keeps the prototype dependency-free. The schema avoids SQLite-only
features so it ports to Postgres with type tweaks (TEXT ids, ISO timestamps).
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
-- The three trading businesses under the group.
CREATE TABLE IF NOT EXISTS brands (
    id TEXT PRIMARY KEY,                 -- 'care', 'engineering', 'finance'
    name TEXT NOT NULL,
    sector TEXT NOT NULL,
    default_model TEXT NOT NULL,          -- 'temp', 'perm' or 'both'
    website TEXT,
    privacy_url TEXT,
    postal_address TEXT,
    lia_summary TEXT                      -- legitimate interest assessment, in brief
);

-- Senders. Usually AI assistants, always disclosed as AI in every message
-- they send. is_ai=0 is a person (Tristan) sending AI-drafted, human-approved
-- email under their own name: the lean launch uses one such mailbox.
CREATE TABLE IF NOT EXISTS assistants (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,           -- e.g. 'Ava, AI recruitment assistant'
    is_ai INTEGER NOT NULL DEFAULT 1,
    brand_id TEXT REFERENCES brands(id),  -- NULL means works across all brands
    mailbox TEXT NOT NULL,                -- sending address
    mailbox_started_on TEXT NOT NULL,     -- for warm-up ramp
    calendly_url TEXT
);

CREATE TABLE IF NOT EXISTS organisations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT,
    industry TEXT,
    size TEXT,
    location TEXT,
    notes TEXT,
    UNIQUE(domain)
);

-- Candidates and client contacts share one table; kind tells them apart.
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('candidate','client')),
    brand_id TEXT NOT NULL REFERENCES brands(id),
    first_name TEXT, last_name TEXT,
    email TEXT NOT NULL,
    email_type TEXT NOT NULL DEFAULT 'unknown',   -- 'corporate' | 'personal' | 'unknown'
    phone TEXT,
    title TEXT,
    organisation_id TEXT REFERENCES organisations(id),
    location TEXT,
    linkedin_url TEXT,                    -- stored as a reference only, never scraped
    headline TEXT,
    summary TEXT,                         -- free text from the import or added by hand
    skills TEXT,                          -- comma separated
    qualifications TEXT,                  -- e.g. NMC PIN status, CSCS, ACCA
    seniority TEXT,
    work_preference TEXT,                 -- 'temp' | 'perm' | 'either'
    -- GDPR / PECR
    source TEXT NOT NULL,                 -- 'apollo_csv', 'manual', 'website_form', ...
    source_detail TEXT,
    lawful_basis TEXT NOT NULL,           -- 'legitimate_interests' | 'consent'
    consent_at TEXT,                      -- set when lawful_basis is consent
    art14_notice_sent_at TEXT,            -- first contact must carry the privacy notice
    status TEXT NOT NULL DEFAULT 'new',   -- new|contacted|replied|meeting|placed|not_interested|do_not_contact
    score INTEGER DEFAULT 0,
    owner_assistant_id TEXT REFERENCES assistants(id),
    last_activity_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(email, brand_id)
);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Group-wide suppression. Stores a hash too, so erasure can keep the block.
CREATE TABLE IF NOT EXISTS suppressions (
    email_hash TEXT PRIMARY KEY,
    email TEXT,                           -- cleared on erasure, hash kept
    reason TEXT NOT NULL,                 -- unsubscribe|hard_bounce|complaint|erasure|manual
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sequences (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    brand_id TEXT NOT NULL REFERENCES brands(id),
    audience TEXT NOT NULL CHECK (audience IN ('candidate','client')),
    goal TEXT NOT NULL,
    steps_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enrollments (
    id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    sequence_id TEXT NOT NULL REFERENCES sequences(id),
    assistant_id TEXT NOT NULL REFERENCES assistants(id),
    current_step INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',  -- active|completed|stopped
    stop_reason TEXT,
    next_due_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(contact_id, sequence_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    contact_id TEXT REFERENCES contacts(id) ON DELETE CASCADE,
    enrollment_id TEXT REFERENCES enrollments(id) ON DELETE CASCADE,
    assistant_id TEXT REFERENCES assistants(id),
    direction TEXT NOT NULL CHECK (direction IN ('out','in')),
    step INTEGER,
    subject TEXT,
    body TEXT,
    status TEXT NOT NULL,     -- draft|approved|queued|sent|failed|blocked|received
    block_reason TEXT,
    intent TEXT,              -- inbound: interested|not_now|not_interested|unsubscribe|ooo|question
    thread_key TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    contact_id TEXT REFERENCES contacts(id) ON DELETE SET NULL,
    assistant_id TEXT REFERENCES assistants(id),
    host_name TEXT NOT NULL,
    host_email TEXT NOT NULL,
    invitee_name TEXT, invitee_email TEXT,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    calendly_event_uri TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'booked', -- booked|cancelled|held|no_show
    briefing TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    subject TEXT,
    detail TEXT
);

-- Tristan's LinkedIn list. People he researched himself (by hand, in LinkedIn
-- or Sales Navigator) or that came from a compliant data provider. Nothing in
-- this CRM visits LinkedIn: Tristan sends every invitation and message by hand.
CREATE TABLE IF NOT EXISTS linkedin_targets (
    id TEXT PRIMARY KEY,
    brand_id TEXT NOT NULL REFERENCES brands(id),
    kind TEXT NOT NULL CHECK (kind IN ('candidate','client')),
    first_name TEXT NOT NULL,
    last_name TEXT,
    title TEXT,
    company TEXT,
    company_domain TEXT,
    location TEXT,
    profile_url TEXT NOT NULL UNIQUE,
    why TEXT,                             -- Tristan's reason / hook, e.g. 'new FD, team growing'
    source TEXT NOT NULL DEFAULT 'manual',
    priority INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'queued', -- queued|listed|invited|accepted|messaged|replied|declined|skipped
    note_draft TEXT,                      -- connection note, within LinkedIn's character limit
    dm_draft TEXT,                        -- first message after they accept
    listed_on TEXT,                       -- date it went on a daily list
    invited_at TEXT,
    accepted_at TEXT,
    contact_id TEXT REFERENCES contacts(id) ON DELETE SET NULL,
    email_lookup TEXT,                    -- last lookup outcome
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_li_status ON linkedin_targets(status, priority);
CREATE INDEX IF NOT EXISTS ix_enrol_due ON enrollments(status, next_due_at);
CREATE INDEX IF NOT EXISTS ix_msg_status ON messages(status, assistant_id);
CREATE INDEX IF NOT EXISTS ix_msg_sent ON messages(assistant_id, sent_at);
"""

DEFAULT_BRANDS = [
    # (id, name, sector, default_model, lia_summary)
    ("care", "Wrenfield Care", "Nursing, medical and care", "perm",
     "Contacting healthcare professionals about relevant roles they are qualified for; "
     "minimal data, opt-out in every message, no special-category data collected by outreach."),
    ("engineering", "Wrenfield Build", "Engineering, construction and technical trades", "both",
     "Contacting engineers, trades and hiring managers about relevant contract and permanent work; "
     "business contact data only, opt-out in every message."),
    ("finance", "Wrenfield Finance", "Accounting and finance", "perm",
     "Contacting finance professionals and finance leaders about relevant permanent and interim roles; "
     "business contact data only, opt-out in every message."),
]


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(conn: sqlite3.Connection, base_url: str = "http://localhost:8080") -> None:
    conn.executescript(SCHEMA)
    # Databases created before is_ai existed.
    if "is_ai" not in {r[1] for r in conn.execute("PRAGMA table_info(assistants)")}:
        conn.execute("ALTER TABLE assistants ADD COLUMN is_ai INTEGER NOT NULL DEFAULT 1")
    for bid, name, sector, model, lia in DEFAULT_BRANDS:
        conn.execute(
            "INSERT OR IGNORE INTO brands (id, name, sector, default_model, website, privacy_url, postal_address, lia_summary)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (bid, name, sector, model, f"{base_url}/{bid}", f"{base_url}/{bid}/privacy",
             "Registered office address goes here", lia),
        )
    conn.commit()


def audit(conn: sqlite3.Connection, actor: str, action: str, subject: str = "", detail: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_log (at, actor, action, subject, detail) VALUES (?,?,?,?,?)",
        (now(), actor, action, subject, detail),
    )
