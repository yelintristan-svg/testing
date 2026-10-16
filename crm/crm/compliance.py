"""UK GDPR and PECR rules the engine enforces before any email is sent.

The short version, as the code applies it:

* PECR reg. 22: unsolicited marketing email to *individual subscribers*
  (personal addresses, sole traders) needs prior consent. Corporate
  addresses (someone@theircompany.co.uk) may be emailed without consent,
  provided every message identifies the sender and offers a working opt-out.
  So: personal or unknown address + no consent = blocked.
* UK GDPR Art. 6(1)(f): business outreach relies on legitimate interests,
  backed by the brand's LIA (stored on the brand).
* UK GDPR Art. 14: when data came from a third party (e.g. Apollo), the
  first message must say where we got it and link the privacy notice.
* Objection / unsubscribe is absolute and group-wide (all three brands).
* Erasure deletes the person but keeps a hash on the suppression list so
  a future re-import cannot email them again.
* Retention: contacts with no activity for CRM_RETENTION_DAYS are purged.

This is engineering, not legal advice; Tristan should have the privacy
notices and LIAs checked before going live.
"""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
from datetime import datetime, timedelta, timezone

from . import db

# Common free/consumer mail domains. Anything here is treated as a personal
# address. Unknown domains are also treated cautiously (see classify_email).
PERSONAL_DOMAINS = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.co.uk", "outlook.com",
    "live.com", "live.co.uk", "yahoo.com", "yahoo.co.uk", "icloud.com", "me.com",
    "aol.com", "btinternet.com", "sky.com", "virginmedia.com", "talktalk.net",
    "protonmail.com", "proton.me", "gmx.com", "mail.com", "ymail.com", "msn.com",
}


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def email_hash(email: str) -> str:
    return hashlib.sha256(normalise_email(email).encode()).hexdigest()


def classify_email(email: str, org_domain: str | None = None) -> str:
    domain = normalise_email(email).rpartition("@")[2]
    if not domain:
        return "unknown"
    if domain in PERSONAL_DOMAINS:
        return "personal"
    if org_domain and (domain == org_domain.lower() or domain.endswith("." + org_domain.lower())):
        return "corporate"
    # A non-free domain is most likely corporate, but a sole trader's own
    # domain counts as an individual subscriber under PECR. Without an
    # organisation to match against we can't tell, so mark it unknown.
    return "corporate" if org_domain else "unknown"


def is_suppressed(conn: sqlite3.Connection, email: str) -> bool:
    row = conn.execute("SELECT 1 FROM suppressions WHERE email_hash=?", (email_hash(email),)).fetchone()
    return row is not None


def suppress(conn: sqlite3.Connection, email: str, reason: str, actor: str = "system", keep_address: bool = True) -> None:
    conn.execute(
        "INSERT INTO suppressions (email_hash, email, reason, created_at) VALUES (?,?,?,?)"
        " ON CONFLICT(email_hash) DO UPDATE SET reason=excluded.reason",
        (email_hash(email), normalise_email(email) if keep_address else None, reason, db.now()),
    )
    # Stop every live sequence for this address, across all brands.
    conn.execute(
        "UPDATE enrollments SET status='stopped', stop_reason=? WHERE status='active' AND contact_id IN"
        " (SELECT id FROM contacts WHERE email=?)",
        (reason, normalise_email(email)),
    )
    conn.execute(
        "UPDATE contacts SET status='do_not_contact', updated_at=? WHERE email=?",
        (db.now(), normalise_email(email)),
    )
    conn.execute(
        "UPDATE messages SET status='blocked', block_reason=? WHERE direction='out' AND status IN ('draft','approved','queued')"
        " AND contact_id IN (SELECT id FROM contacts WHERE email=?)",
        (reason, normalise_email(email)),
    )
    db.audit(conn, actor, "suppress", email_hash(email), reason)


def unsubscribe_token(secret: str, email: str) -> str:
    return hmac.new(secret.encode(), normalise_email(email).encode(), hashlib.sha256).hexdigest()[:32]


def unsubscribe_url(base_url: str, secret: str, email: str) -> str:
    from urllib.parse import quote
    e = normalise_email(email)
    return f"{base_url}/u?e={quote(e)}&t={unsubscribe_token(secret, e)}"


def verify_unsubscribe(secret: str, email: str, token: str) -> bool:
    return hmac.compare_digest(unsubscribe_token(secret, email), token or "")


def can_email(conn: sqlite3.Connection, contact: sqlite3.Row) -> tuple[bool, str]:
    """Return (allowed, reason). Called for every outbound message."""
    if is_suppressed(conn, contact["email"]):
        return False, "suppressed"
    if contact["status"] == "do_not_contact":
        return False, "do_not_contact"
    if contact["lawful_basis"] == "consent":
        return (True, "consent") if contact["consent_at"] else (False, "consent_missing")
    # Legitimate interests path: only corporate subscribers under PECR.
    if contact["email_type"] != "corporate":
        return False, f"pecr_{contact['email_type']}_address_needs_consent"
    return True, "legitimate_interests_corporate"


def footer(conn: sqlite3.Connection, contact: sqlite3.Row, assistant: sqlite3.Row,
           base_url: str, secret: str, unsub_mode: str = "link") -> str:
    """Signature, disclosures and opt-out. unsub_mode='reply' asks for a reply instead of
    a link, for when the CRM's unsubscribe page isn't hosted yet (PECR needs a simple,
    free way to opt out; a reply counts)."""
    brand = conn.execute("SELECT * FROM brands WHERE id=?", (contact["brand_id"],)).fetchone()
    lines = [
        "--",
        f"{assistant['display_name']} | {brand['name']}",
        "I'm an AI assistant. I work alongside our recruitment team, and a person reviews every conversation."
        if assistant["is_ai"] else "",
        brand["postal_address"] or "",
    ]
    if not contact["art14_notice_sent_at"]:
        src = contact["source_detail"] or contact["source"]
        lines.append(
            f"We found your professional details via {src}. Our privacy notice explains how we use them "
            f"and your rights: {brand['privacy_url']}"
        )
    if unsub_mode == "reply":
        lines.append("Not interested? Just reply \"unsubscribe\" and we won't email you again.")
    else:
        lines.append(
            "Not interested? One click and we won't email you again from any of our brands: "
            + unsubscribe_url(base_url, secret, contact["email"])
        )
    return "\n".join(line for line in lines if line)


def erase(conn: sqlite3.Connection, email: str, actor: str) -> int:
    """Right to erasure. Deletes the person everywhere, keeps a hashed block."""
    e = normalise_email(email)
    suppress(conn, e, "erasure", actor=actor, keep_address=False)
    ids = [r["id"] for r in conn.execute("SELECT id FROM contacts WHERE email=?", (e,))]
    for cid in ids:
        conn.execute("UPDATE meetings SET invitee_email=NULL, invitee_name=NULL, briefing=NULL WHERE contact_id=?", (cid,))
        conn.execute("DELETE FROM contacts WHERE id=?", (cid,))
    conn.execute("UPDATE meetings SET invitee_email=NULL, invitee_name=NULL WHERE invitee_email=?", (e,))
    conn.execute("DELETE FROM prospect_people WHERE email=?", (e,))
    db.audit(conn, actor, "erase", email_hash(e), f"{len(ids)} contact records")
    conn.commit()
    return len(ids)


def subject_access_export(conn: sqlite3.Connection, email: str) -> dict:
    """Everything held about one person, for a subject access request."""
    e = normalise_email(email)
    out: dict = {"email": e, "contacts": [], "suppressed": is_suppressed(conn, e)}
    for c in conn.execute("SELECT * FROM contacts WHERE email=?", (e,)):
        cid = c["id"]
        out["contacts"].append({
            "record": dict(c),
            "notes": [dict(r) for r in conn.execute("SELECT * FROM notes WHERE contact_id=?", (cid,))],
            "messages": [dict(r) for r in conn.execute("SELECT * FROM messages WHERE contact_id=?", (cid,))],
            "meetings": [dict(r) for r in conn.execute("SELECT * FROM meetings WHERE contact_id=?", (cid,))],
            "enrollments": [dict(r) for r in conn.execute("SELECT * FROM enrollments WHERE contact_id=?", (cid,))],
        })
    return out


def purge_stale(conn: sqlite3.Connection, retention_days: int, actor: str = "retention") -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    rows = conn.execute(
        "SELECT id FROM contacts WHERE status NOT IN ('meeting','placed')"
        " AND COALESCE(last_activity_at, created_at) < ?",
        (cutoff,),
    ).fetchall()
    for r in rows:
        conn.execute("DELETE FROM contacts WHERE id=?", (r["id"],))
    # People prospecting looked at but never added: keep their names no longer than contacts.
    conn.execute("DELETE FROM prospect_people WHERE contact_id IS NULL AND created_at < ?", (cutoff,))
    db.audit(conn, actor, "retention_purge", "", f"{len(rows)} contacts older than {retention_days}d")
    conn.commit()
    return len(rows)
