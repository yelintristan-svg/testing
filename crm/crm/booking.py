"""Calendly webhook -> meeting on Tristan's calendar -> handoff.

How booking reaches Tristan's calendar: the assistants' booking links all
point at event types owned by Tristan's Calendly account, which is
connected to his Google or Outlook calendar. So any booking an assistant
gets lands on Tristan's calendar automatically, with him as host. This
module records the meeting, stops outreach, writes Tristan a briefing, and
drafts the assistant's honest handoff note.

Calendly webhook docs: events `invitee.created` and `invitee.canceled`,
signed with the `Calendly-Webhook-Signature: t=<ts>,v1=<hex>` header,
where v1 = HMAC-SHA256(signing_key, f"{t}.{raw_body}").
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from . import compliance, db
from .settings import Settings

TOLERANCE_SECONDS = 180


def verify_signature(signing_key: str, header: str, raw_body: bytes, now: float | None = None) -> bool:
    if not signing_key or not header:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    t, v1 = parts.get("t"), parts.get("v1")
    if not t or not v1:
        return False
    if abs((now or time.time()) - int(t)) > TOLERANCE_SECONDS:
        return False
    expected = hmac.new(signing_key.encode(), f"{t}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


def sign(signing_key: str, raw_body: bytes, t: int | None = None) -> str:
    """Produce a header the way Calendly does. Used by tests and the simulator."""
    t = t or int(time.time())
    v1 = hmac.new(signing_key.encode(), f"{t}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return f"t={t},v1={v1}"


def handle_webhook(conn: sqlite3.Connection, settings: Settings, event: dict, outbox: Path | None = None) -> dict:
    kind = event.get("event")
    p = event.get("payload", {})
    sched = p.get("scheduled_event", {})
    uri = sched.get("uri") or p.get("event")
    if kind == "invitee.canceled":
        conn.execute("UPDATE meetings SET status='cancelled' WHERE calendly_event_uri=?", (uri,))
        conn.commit()
        return {"status": "cancelled", "uri": uri}
    if kind != "invitee.created":
        return {"status": "ignored", "event": kind}

    email = compliance.normalise_email(p.get("email", ""))
    tracking = p.get("tracking") or {}
    contact = None
    if tracking.get("utm_content"):
        contact = conn.execute("SELECT * FROM contacts WHERE id=?", (tracking["utm_content"],)).fetchone()
    if contact is None and email:
        contact = conn.execute("SELECT * FROM contacts WHERE email=? ORDER BY last_activity_at DESC", (email,)).fetchone()
    assistant_id = tracking.get("utm_campaign") or (contact["owner_assistant_id"] if contact else None)
    if assistant_id and not conn.execute("SELECT 1 FROM assistants WHERE id=?", (assistant_id,)).fetchone():
        assistant_id = None
    members = sched.get("event_memberships") or [{}]
    host_email = members[0].get("user_email") or settings.recruiter_email

    briefing = build_briefing(conn, contact, p) if contact else "Booked by someone not yet in the CRM."
    mid = db.new_id("mtg")
    try:
        conn.execute(
            "INSERT INTO meetings (id, contact_id, assistant_id, host_name, host_email, invitee_name, invitee_email,"
            " starts_at, ends_at, calendly_event_uri, briefing, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (mid, contact["id"] if contact else None, assistant_id, settings.recruiter_name, host_email,
             p.get("name"), email, sched.get("start_time"), sched.get("end_time"), uri, briefing, db.now()))
    except sqlite3.IntegrityError:
        return {"status": "duplicate", "uri": uri}

    if contact:
        ts = db.now()
        conn.execute("UPDATE contacts SET status='meeting', score=score+100, last_activity_at=?, updated_at=? WHERE id=?",
                     (ts, ts, contact["id"]))
        conn.execute("UPDATE enrollments SET status='stopped', stop_reason='meeting_booked'"
                     " WHERE contact_id=? AND status='active'", (contact["id"],))
        conn.execute("UPDATE messages SET status='blocked', block_reason='meeting_booked' WHERE contact_id=?"
                     " AND direction='out' AND status IN ('draft','approved','queued')", (contact["id"],))
        if assistant_id:
            a = conn.execute("SELECT * FROM assistants WHERE id=?", (assistant_id,)).fetchone()
            _queue_handoff(conn, settings, contact, a, sched)
    db.audit(conn, "calendly", "meeting_booked", mid, uri or "")
    conn.commit()
    if outbox:
        Path(outbox).mkdir(parents=True, exist_ok=True)
        (Path(outbox) / f"{mid}.ics").write_text(to_ics(mid, settings, p, sched, briefing))
    return {"status": "booked", "meeting_id": mid, "contact_id": contact["id"] if contact else None}


def _queue_handoff(conn, settings: Settings, contact, assistant, sched) -> None:
    """The assistant's confirmation. Honest framing: it's an AI that passed the profile on."""
    start = sched.get("start_time", "")
    try:
        when = datetime.fromisoformat(start.replace("Z", "+00:00")).strftime("%A %d %B at %H:%M UTC")
    except ValueError:
        when = start
    name = contact["first_name"] or "there"
    body = (
        f"Hi {name},\n\nThanks for booking. You're confirmed with {settings.recruiter_name}, our "
        f"{settings.recruiter_title}, on {when}. I passed your details to {settings.recruiter_name} because your "
        f"experience looked like a strong fit, and they'll have read through it before you speak.\n\n"
        f"If anything changes, the link in your calendar invite lets you reschedule."
    )
    # Transactional, not marketing: approved straight away, no sequence attached.
    conn.execute(
        "INSERT INTO messages (id, contact_id, assistant_id, direction, subject, body, status, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (db.new_id("msg"), contact["id"], assistant["id"], "out", f"Confirmed: your call with {settings.recruiter_name}",
         body, "approved", db.now()))


def build_briefing(conn: sqlite3.Connection, contact: sqlite3.Row, payload: dict) -> str:
    org = conn.execute("SELECT * FROM organisations WHERE id=?", (contact["organisation_id"],)).fetchone() \
        if contact["organisation_id"] else None
    lines = [
        f"{contact['first_name'] or ''} {contact['last_name'] or ''}".strip() + f" ({contact['kind']}, {contact['brand_id']})",
        f"Title: {contact['title'] or '-'}" + (f" at {org['name']}" if org else ""),
        f"Location: {contact['location'] or '-'}  Preference: {contact['work_preference'] or '-'}",
        f"Skills: {contact['skills'] or '-'}",
        f"Qualifications: {contact['qualifications'] or '-'}",
        f"LinkedIn: {contact['linkedin_url'] or '-'}",
        f"Source: {contact['source']} ({contact['lawful_basis']})",
    ]
    for qa in payload.get("questions_and_answers") or []:
        lines.append(f"Q: {qa.get('question')} A: {qa.get('answer')}")
    convo = conn.execute(
        "SELECT direction, subject, intent, substr(body,1,400) AS body FROM messages WHERE contact_id=?"
        " AND status IN ('sent','received') ORDER BY created_at", (contact["id"],)).fetchall()
    if convo:
        lines.append("Conversation so far:")
        for m in convo:
            tag = "us" if m["direction"] == "out" else f"them ({m['intent']})"
            lines.append(f"- {tag}: {m['subject']}: {m['body'].splitlines()[0] if m['body'] else ''}")
    return "\n".join(lines)


def to_ics(uid: str, settings: Settings, payload: dict, sched: dict, briefing: str) -> str:
    def fmt(ts: str) -> str:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y%m%dT%H%M%SZ")
    desc = briefing.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")
    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//recruitment-crm//EN", "BEGIN:VEVENT",
        f"UID:{uid}@crm", f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{fmt(sched['start_time'])}", f"DTEND:{fmt(sched['end_time'])}",
        f"SUMMARY:Call: {payload.get('name', 'invitee')} with {settings.recruiter_name}",
        f"ORGANIZER:mailto:{settings.recruiter_email}",
        f"ATTENDEE:mailto:{payload.get('email', '')}",
        f"DESCRIPTION:{desc}", "END:VEVENT", "END:VCALENDAR", "",
    ])


def sample_event(contact: sqlite3.Row | None, assistant_id: str, start: str, end: str,
                 email: str | None = None) -> dict:
    return {
        "event": "invitee.created",
        "payload": {
            "email": email or (contact["email"] if contact else ""),
            "name": f"{contact['first_name']} {contact['last_name']}" if contact else "Walk-in",
            "uri": f"https://api.calendly.com/scheduled_events/SIM/invitees/{db.new_id('inv')}",
            "scheduled_event": {
                "uri": f"https://api.calendly.com/scheduled_events/{db.new_id('evt')}",
                "start_time": start, "end_time": end,
                "event_memberships": [{"user_email": "tristan@example.com"}],
            },
            "tracking": {"utm_source": "crm", "utm_campaign": assistant_id,
                         "utm_content": contact["id"] if contact else None},
            "questions_and_answers": [{"question": "What would you like to discuss?", "answer": "Next role"}],
        },
    }


def dumps(event: dict) -> bytes:
    return json.dumps(event, separators=(",", ":")).encode()
