"""Sequences, drafting, throttled sending and inbound handling.

Lifecycle of one email:
  enrollment due -> draft (Claude) -> [review] -> approved -> send window +
  throttle check -> compliance re-check -> sent -> next step scheduled.

Run `tick` from cron every few minutes. It is idempotent: an enrollment
never has more than one unsent message at a time.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from . import compliance, db, mailer as mailer_mod
from .personalise import DraftRejected, Writer
from .settings import Settings

OPEN_STATUSES = ("draft", "approved", "queued")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


# -- setup --------------------------------------------------------------------

def load_sequence(conn: sqlite3.Connection, path: Path | str) -> str:
    spec = json.loads(Path(path).read_text())
    conn.execute(
        "INSERT INTO sequences (id, name, brand_id, audience, goal, steps_json) VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(id) DO UPDATE SET name=excluded.name, goal=excluded.goal, steps_json=excluded.steps_json",
        (spec["id"], spec["name"], spec["brand_id"], spec["audience"], spec["goal"], json.dumps(spec["steps"])),
    )
    conn.commit()
    return spec["id"]


def add_assistant(conn: sqlite3.Connection, aid: str, display_name: str, mailbox: str, calendly_url: str,
                  brand_id: str | None = None, started_on: str | None = None, is_ai: bool = True) -> None:
    """Add a sender. is_ai=False is a person sending under their own name."""
    if compliance.classify_email(mailbox) == "personal":
        raise ValueError(f"{mailbox} is a personal mailbox. Send from a business domain you own "
                         "(see blueprint/finance-launch-plan.md, 'Email').")
    conn.execute(
        "INSERT INTO assistants (id, display_name, is_ai, brand_id, mailbox, mailbox_started_on, calendly_url)"
        " VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,"
        " is_ai=excluded.is_ai, mailbox=excluded.mailbox, calendly_url=excluded.calendly_url,"
        " brand_id=excluded.brand_id",
        (aid, display_name, int(is_ai), brand_id, mailbox, started_on or db.now()[:10], calendly_url),
    )
    conn.commit()


def enroll(conn: sqlite3.Connection, contact_id: str, sequence_id: str, assistant_id: str,
           start_at: datetime | None = None) -> tuple[str | None, str]:
    c = conn.execute("SELECT * FROM contacts WHERE id=?", (contact_id,)).fetchone()
    seq = conn.execute("SELECT * FROM sequences WHERE id=?", (sequence_id,)).fetchone()
    if c is None or seq is None:
        return None, "not_found"
    if c["kind"] != seq["audience"] or c["brand_id"] != seq["brand_id"]:
        return None, "audience_or_brand_mismatch"
    ok, reason = compliance.can_email(conn, c)
    if not ok:
        return None, reason
    eid = db.new_id("enr")
    try:
        conn.execute(
            "INSERT INTO enrollments (id, contact_id, sequence_id, assistant_id, next_due_at, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (eid, contact_id, sequence_id, assistant_id, _iso(start_at or datetime.now(timezone.utc)), db.now()),
        )
    except sqlite3.IntegrityError:
        return None, "already_enrolled"
    conn.execute("UPDATE contacts SET owner_assistant_id=COALESCE(owner_assistant_id, ?) WHERE id=?",
                 (assistant_id, contact_id))
    conn.commit()
    return eid, "enrolled"


# -- drafting -----------------------------------------------------------------

def draft_due(conn: sqlite3.Connection, settings: Settings, writer: Writer, now: datetime | None = None,
              limit: int = 200) -> dict:
    now = now or datetime.now(timezone.utc)
    counts: dict[str, int] = {}
    rows = conn.execute(
        "SELECT e.* FROM enrollments e WHERE e.status='active' AND e.next_due_at<=?"
        " AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.enrollment_id=e.id AND m.status IN (?,?,?))"
        " ORDER BY e.next_due_at LIMIT ?",
        (_iso(now), *OPEN_STATUSES, limit),
    ).fetchall()
    for e in rows:
        seq = conn.execute("SELECT * FROM sequences WHERE id=?", (e["sequence_id"],)).fetchone()
        steps = json.loads(seq["steps_json"])
        if e["current_step"] >= len(steps):
            conn.execute("UPDATE enrollments SET status='completed' WHERE id=?", (e["id"],))
            counts["completed"] = counts.get("completed", 0) + 1
            continue
        contact = conn.execute("SELECT * FROM contacts WHERE id=?", (e["contact_id"],)).fetchone()
        ok, reason = compliance.can_email(conn, contact)
        if not ok:
            conn.execute("UPDATE enrollments SET status='stopped', stop_reason=? WHERE id=?", (reason, e["id"]))
            counts[f"stopped_{reason}"] = counts.get(f"stopped_{reason}", 0) + 1
            continue
        assistant = conn.execute("SELECT * FROM assistants WHERE id=?", (e["assistant_id"],)).fetchone()
        step = dict(steps[e["current_step"]], index=e["current_step"], sequence_name=seq["name"], goal=seq["goal"])
        previous = conn.execute(
            "SELECT subject, body FROM messages WHERE enrollment_id=? AND direction='out' AND status='sent'"
            " ORDER BY sent_at", (e["id"],)).fetchall()
        try:
            d = writer.draft(conn, contact, assistant, step, previous)
        except DraftRejected as exc:
            db.audit(conn, "drafter", "draft_rejected", e["id"], str(exc))
            # Try again on the next tick, but not straight away.
            conn.execute("UPDATE enrollments SET next_due_at=? WHERE id=?", (_iso(now + timedelta(hours=1)), e["id"]))
            counts["rejected"] = counts.get("rejected", 0) + 1
            continue
        needs_review = settings.require_review and step["index"] == 0
        conn.execute(
            "INSERT INTO messages (id, contact_id, enrollment_id, assistant_id, direction, step, subject, body,"
            " status, thread_key, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (db.new_id("msg"), contact["id"], e["id"], assistant["id"], "out", step["index"], d.subject, d.body,
             "draft" if needs_review else "approved", e["id"], db.now()),
        )
        key = "drafted_for_review" if needs_review else "drafted_auto_approved"
        counts[key] = counts.get(key, 0) + 1
    conn.commit()
    return counts


def approve(conn: sqlite3.Connection, message_ids: list[str] | None = None, actor: str = "tristan",
            edits: dict | None = None) -> int:
    if message_ids is None:
        message_ids = [r["id"] for r in conn.execute("SELECT id FROM messages WHERE status='draft'")]
    for mid in message_ids:
        if edits and mid in edits:
            conn.execute("UPDATE messages SET subject=?, body=? WHERE id=?", (*edits[mid], mid))
        conn.execute("UPDATE messages SET status='approved' WHERE id=? AND status='draft'", (mid,))
        db.audit(conn, actor, "approve", mid)
    conn.commit()
    return len(message_ids)


# -- throttled sending --------------------------------------------------------

def mailbox_cap(settings: Settings, started_on: str, today) -> int:
    """Warm-up ramp: start low, grow linearly to the daily cap."""
    age = (today - datetime.fromisoformat(started_on).date()).days
    if age >= settings.warmup_days:
        return settings.daily_cap
    span = settings.daily_cap - settings.warmup_start_cap
    return settings.warmup_start_cap + int(span * max(age, 0) / settings.warmup_days)


def capacity(conn: sqlite3.Connection, settings: Settings, assistant: sqlite3.Row, now: datetime) -> tuple[int, str]:
    tz = ZoneInfo(settings.timezone)
    local = now.astimezone(tz)
    if local.weekday() >= 5:
        return 0, "weekend"
    if not (settings.send_window_start <= local.hour < settings.send_window_end):
        return 0, "outside_send_window"
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE assistant_id=? AND status='sent' AND sent_at>=?",
        (assistant["id"], _iso(day_start))).fetchone()[0]
    sent_hour = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE assistant_id=? AND status='sent' AND sent_at>=?",
        (assistant["id"], _iso(now - timedelta(hours=1)))).fetchone()[0]
    last = conn.execute("SELECT MAX(sent_at) FROM messages WHERE assistant_id=? AND status='sent'",
                        (assistant["id"],)).fetchone()[0]
    cap = mailbox_cap(settings, assistant["mailbox_started_on"], local.date())
    if sent_today >= cap:
        return 0, f"daily_cap_{cap}"
    if sent_hour >= settings.hourly_cap:
        return 0, "hourly_cap"
    if last and (now - _parse(last)).total_seconds() < settings.min_gap_seconds:
        return 0, "min_gap"
    # One message per tick per mailbox keeps natural spacing; cron supplies the cadence.
    return 1, "ok"


def booking_link(assistant: sqlite3.Row, contact: sqlite3.Row) -> str:
    name = " ".join(x for x in (contact["first_name"], contact["last_name"]) if x)
    q = urlencode({"name": name, "email": contact["email"], "utm_source": "crm",
                   "utm_campaign": assistant["id"], "utm_content": contact["id"]})
    return f"{assistant['calendly_url']}?{q}"


def send_due(conn: sqlite3.Connection, settings: Settings, mailer=None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    mailer = mailer or mailer_mod.from_settings(settings)
    counts: dict[str, int] = {}
    for a in conn.execute("SELECT * FROM assistants").fetchall():
        if not a["is_ai"] and settings.hand_send:
            continue  # a person's mailbox: they send from the daily list and log it (crm sent)
        room, why = capacity(conn, settings, a, now)
        if room == 0:
            counts[f"held_{why}"] = counts.get(f"held_{why}", 0) + 1
            continue
        msgs = conn.execute(
            "SELECT * FROM messages WHERE assistant_id=? AND status='approved' ORDER BY created_at LIMIT ?",
            (a["id"], room)).fetchall()
        for m in msgs:
            c = conn.execute("SELECT * FROM contacts WHERE id=?", (m["contact_id"],)).fetchone()
            ok, reason = compliance.can_email(conn, c) if c else (False, "contact_deleted")
            if not ok:
                conn.execute("UPDATE messages SET status='blocked', block_reason=? WHERE id=?", (reason, m["id"]))
                counts[f"blocked_{reason}"] = counts.get(f"blocked_{reason}", 0) + 1
                continue
            body = render_body(conn, settings, a, c, m)
            unsub = compliance.unsubscribe_url(settings.public_base_url, settings.unsubscribe_secret, c["email"])
            email = mailer_mod.build(a["display_name"], a["mailbox"], c["email"], m["subject"], body, unsub)
            try:
                mailer.send(email, m["id"])
            except Exception as exc:  # transport error: keep the message, retry next tick
                db.audit(conn, "sender", "send_failed", m["id"], str(exc))
                counts["failed"] = counts.get("failed", 0) + 1
                continue
            _record_sent(conn, m, c, body, now)
            counts["sent"] = counts.get("sent", 0) + 1
    conn.commit()
    return counts


def render_body(conn: sqlite3.Connection, settings: Settings, assistant: sqlite3.Row, contact: sqlite3.Row,
                message: sqlite3.Row) -> str:
    """The email exactly as it goes out: booking link filled in, footer added."""
    body = message["body"].replace("{BOOKING_LINK}", booking_link(assistant, contact))
    return body + "\n\n" + compliance.footer(conn, contact, assistant, settings.public_base_url,
                                              settings.unsubscribe_secret, settings.unsub_mode)


def _record_sent(conn: sqlite3.Connection, m: sqlite3.Row, c: sqlite3.Row, body: str, now: datetime) -> None:
    ts = _iso(now)
    conn.execute("UPDATE messages SET status='sent', sent_at=?, body=? WHERE id=?", (ts, body, m["id"]))
    conn.execute(
        "UPDATE contacts SET status=CASE WHEN status='new' THEN 'contacted' ELSE status END,"
        " art14_notice_sent_at=COALESCE(art14_notice_sent_at, ?), last_activity_at=?, updated_at=? WHERE id=?",
        (ts, ts, ts, c["id"]))
    if m["enrollment_id"]:
        _advance(conn, m["enrollment_id"], now)


def mark_sent(conn: sqlite3.Connection, settings: Settings, message_ids: list[str] | None = None,
              sender_id: str | None = None, now: datetime | None = None) -> dict:
    """Log emails a person sent by hand from the daily list (all of theirs if no ids given)."""
    now = now or datetime.now(timezone.utc)
    q = ("SELECT m.* FROM messages m JOIN assistants a ON a.id=m.assistant_id WHERE a.is_ai=0"
         " AND m.direction='out' AND m.status IN ('draft','approved')")
    params: list = []
    if message_ids:
        q += f" AND m.id IN ({','.join('?' * len(message_ids))})"; params += message_ids
    if sender_id:
        q += " AND m.assistant_id=?"; params.append(sender_id)
    counts: dict[str, int] = {}
    for m in conn.execute(q, params).fetchall():
        c = conn.execute("SELECT * FROM contacts WHERE id=?", (m["contact_id"],)).fetchone()
        ok, reason = compliance.can_email(conn, c) if c else (False, "contact_deleted")
        if not ok:
            conn.execute("UPDATE messages SET status='blocked', block_reason=? WHERE id=?", (reason, m["id"]))
            counts[f"blocked_{reason}"] = counts.get(f"blocked_{reason}", 0) + 1
            continue
        a = conn.execute("SELECT * FROM assistants WHERE id=?", (m["assistant_id"],)).fetchone()
        _record_sent(conn, m, c, render_body(conn, settings, a, c, m), now)
        db.audit(conn, "tristan", "hand_sent", m["id"])
        counts["sent"] = counts.get("sent", 0) + 1
    conn.commit()
    return counts


def _advance(conn: sqlite3.Connection, enrollment_id: str, sent_at: datetime) -> None:
    e = conn.execute("SELECT * FROM enrollments WHERE id=?", (enrollment_id,)).fetchone()
    if e is None:
        return
    steps = json.loads(conn.execute("SELECT steps_json FROM sequences WHERE id=?", (e["sequence_id"],)).fetchone()[0])
    nxt = e["current_step"] + 1
    if nxt >= len(steps):
        conn.execute("UPDATE enrollments SET current_step=?, status='completed' WHERE id=?", (nxt, e["id"]))
    else:
        due = sent_at + timedelta(days=steps[nxt]["delay_days"])
        conn.execute("UPDATE enrollments SET current_step=?, next_due_at=? WHERE id=?", (nxt, _iso(due), e["id"]))


def tick(conn: sqlite3.Connection, settings: Settings, writer: Writer | None = None, mailer=None,
         now: datetime | None = None) -> dict:
    writer = writer or Writer(settings)
    return {"draft": draft_due(conn, settings, writer, now), "send": send_due(conn, settings, mailer, now)}


# -- inbound ------------------------------------------------------------------

def record_reply(conn: sqlite3.Connection, settings: Settings, from_email: str, subject: str, body: str,
                 writer: Writer | None = None) -> dict:
    """Store an inbound reply, classify it, and stop or adjust outreach.

    Wire this to the mailbox (IMAP poll or the provider's inbound webhook).
    """
    writer = writer or Writer(settings)
    e = compliance.normalise_email(from_email)
    contacts = conn.execute("SELECT * FROM contacts WHERE email=?", (e,)).fetchall()
    result = writer.classify_reply(body)
    intent = result["intent"]
    ts = db.now()
    for c in contacts:
        conn.execute(
            "INSERT INTO messages (id, contact_id, direction, subject, body, status, intent, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (db.new_id("msg"), c["id"], "in", subject, body, "received", intent, ts))
        if intent == "out_of_office":
            continue  # leave the sequence running
        # Any human reply pauses automation; Tristan or the assistant takes it from here.
        conn.execute("UPDATE enrollments SET status='stopped', stop_reason=? WHERE contact_id=? AND status='active'",
                     (f"replied_{intent}", c["id"]))
        conn.execute("UPDATE messages SET status='blocked', block_reason='replied' WHERE contact_id=?"
                     " AND direction='out' AND status IN (?,?,?)", (c["id"], *OPEN_STATUSES))
        new_status = {"interested": "replied", "question": "replied", "not_now": "replied",
                      "not_interested": "not_interested", "wrong_person": "not_interested"}.get(intent, c["status"])
        score = {"interested": 50, "question": 30, "not_now": 10}.get(intent, 0)
        conn.execute("UPDATE contacts SET status=?, score=score+?, last_activity_at=?, updated_at=? WHERE id=?",
                     (new_status, score, ts, ts, c["id"]))
        if result.get("suggested_reply"):
            conn.execute("INSERT INTO notes (id, contact_id, author, body, created_at) VALUES (?,?,?,?,?)",
                         (db.new_id("note"), c["id"], "assistant", "Suggested reply: " + result["suggested_reply"], ts))
    if intent == "unsubscribe":
        compliance.suppress(conn, e, "unsubscribe", actor="reply")
    conn.commit()
    return {"intent": intent, "contacts": len(contacts), "summary": result.get("summary", "")}


def record_bounce(conn: sqlite3.Connection, email: str, hard: bool = True) -> None:
    if hard:
        compliance.suppress(conn, email, "hard_bounce", actor="bounce")
        conn.commit()
