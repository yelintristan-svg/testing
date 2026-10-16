"""Morning standup: what the AI assistants did yesterday and need today.

Produces a Markdown brief per day. Run it before Tristan's day starts (cron
at 07:30); deliver it by email to Tristan or read it out on the standup call.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .engine import mailbox_cap
from .personalise import Writer
from .settings import Settings


def _q(conn, sql, *args):
    return conn.execute(sql, args).fetchall()


def build(conn: sqlite3.Connection, settings: Settings, now: datetime | None = None,
          writer: Writer | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    tz = ZoneInfo(settings.timezone)
    today = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    y0, y1, t1 = today - timedelta(days=1), today, today + timedelta(days=1)
    iso = lambda d: d.astimezone(timezone.utc).isoformat()  # noqa: E731

    out = [f"# Morning standup, {today.strftime('%A %d %B %Y')}", ""]
    facts = []

    meetings = _q(conn, "SELECT m.*, c.title, c.brand_id FROM meetings m LEFT JOIN contacts c ON c.id=m.contact_id"
                        " WHERE m.status='booked' AND m.starts_at>=? AND m.starts_at<? ORDER BY m.starts_at",
                  iso(today), iso(t1))
    out.append(f"## Your calls today ({len(meetings)})")
    for m in meetings:
        start = datetime.fromisoformat(m["starts_at"].replace("Z", "+00:00")).astimezone(tz).strftime("%H:%M")
        out.append(f"- {start} {m['invitee_name']}, {m['title'] or 'unknown title'} ({m['brand_id'] or '?'})")
    if not meetings:
        out.append("- None booked yet.")
    facts.append(f"{len(meetings)} calls today")
    out.append("")

    hot = _q(conn, "SELECT c.first_name, c.last_name, c.title, c.brand_id, m.intent, substr(m.body,1,160) AS snippet"
                   " FROM messages m JOIN contacts c ON c.id=m.contact_id WHERE m.direction='in'"
                   " AND m.intent IN ('interested','question','not_now') AND c.status NOT IN ('meeting','placed')"
                   " ORDER BY m.created_at DESC LIMIT 15")
    out.append(f"## Replies that need you ({len(hot)})")
    for h in hot:
        out.append(f"- **{h['first_name']} {h['last_name']}** ({h['title']}, {h['brand_id']}) {h['intent']}: "
                   f"\"{h['snippet'].strip()}\"")
    if not hot:
        out.append("- Nothing waiting.")
    facts.append(f"{len(hot)} warm replies waiting")
    out.append("")

    drafts = _q(conn, "SELECT COUNT(*) n FROM messages WHERE status='draft'")[0]["n"]
    out.append("## Waiting for your approval")
    out.append(f"- {drafts} first-touch drafts. Run `python -m crm review` to read and approve them.")
    facts.append(f"{drafts} drafts to approve")
    out.append("")

    out.append("## Yesterday, by assistant")
    for a in _q(conn, "SELECT * FROM assistants ORDER BY id"):
        sent = _q(conn, "SELECT COUNT(*) n FROM messages WHERE assistant_id=? AND status='sent' AND sent_at>=? AND sent_at<?",
                  a["id"], iso(y0), iso(y1))[0]["n"]
        replies = _q(conn, "SELECT m.intent, COUNT(*) n FROM messages m JOIN contacts c ON c.id=m.contact_id"
                           " WHERE m.direction='in' AND c.owner_assistant_id=? AND m.created_at>=? AND m.created_at<?"
                           " GROUP BY m.intent", a["id"], iso(y0), iso(y1))
        booked = _q(conn, "SELECT COUNT(*) n FROM meetings WHERE assistant_id=? AND created_at>=? AND created_at<?",
                    a["id"], iso(y0), iso(y1))[0]["n"]
        rtext = ", ".join(f"{r['n']} {r['intent']}" for r in replies) or "no replies"
        cap = mailbox_cap(settings, a["mailbox_started_on"], today.date())
        queued = _q(conn, "SELECT COUNT(*) n FROM messages WHERE assistant_id=? AND status='approved'", a["id"])[0]["n"]
        out.append(f"- **{a['display_name']}**: sent {sent}, {rtext}, booked {booked}. "
                   f"Today: {queued} approved and queued, mailbox cap {cap}/day.")
        facts.append(f"{a['display_name']} sent {sent}, booked {booked}")
    out.append("")

    li = {r["status"]: r["n"] for r in _q(conn, "SELECT status, COUNT(*) n FROM linkedin_targets GROUP BY status")}
    hand = _q(conn, "SELECT COUNT(*) n FROM messages m JOIN assistants a ON a.id=m.assistant_id WHERE a.is_ai=0"
                    " AND m.status IN ('draft','approved')")[0]["n"]
    if li or hand:
        out.append("## Your daily list")
        out.append(f"- {hand} emails ready for you to send. Run `python -m crm daily` to see them.")
        out.append(f"- LinkedIn: {li.get('listed', 0)} invitations to send, {li.get('accepted', 0)} accepted and "
                   f"waiting for your message, {li.get('queued', 0)} people still queued.")
        facts.append(f"{hand} emails and {li.get('listed', 0)} LinkedIn invitations on the daily list")
        out.append("")

    blocked = _q(conn, "SELECT block_reason, COUNT(*) n FROM messages WHERE status='blocked' AND created_at>=?"
                       " GROUP BY block_reason", iso(y0))
    suppressed = _q(conn, "SELECT reason, COUNT(*) n FROM suppressions WHERE created_at>=? GROUP BY reason", iso(y0))
    out.append("## Compliance and deliverability")
    out.append("- Held back: " + (", ".join(f"{b['n']} {b['block_reason']}" for b in blocked) or "none"))
    out.append("- New suppressions: " + (", ".join(f"{s['n']} {s['reason']}" for s in suppressed) or "none"))
    pecr = _q(conn, "SELECT COUNT(*) n FROM contacts WHERE email_type!='corporate' AND lawful_basis!='consent'"
                    " AND status='new'")[0]["n"]
    if pecr:
        out.append(f"- {pecr} imported contacts have personal or unverified addresses, so they can't be emailed "
                   "without consent. Find a work address or invite them to opt in from the website.")
    out.append("")

    pipeline = _q(conn, "SELECT brand_id, kind, status, COUNT(*) n FROM contacts GROUP BY brand_id, kind, status"
                        " ORDER BY brand_id, kind")
    out.append("## Pipeline")
    for p in pipeline:
        out.append(f"- {p['brand_id']} {p['kind']}s {p['status']}: {p['n']}")

    if writer and settings.llm != "offline":
        intro = writer.narrate("; ".join(facts))
        if intro:
            out[1:1] = ["", intro, ""]
    return "\n".join(out) + "\n"
