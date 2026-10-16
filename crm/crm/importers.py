"""Load contacts from compliant sources.

Supported: CSV exports from Apollo (and similar tools: Lusha, Cognism,
ZoomInfo all export comparable headers), a generic CSV, and single records
added by hand. LinkedIn URLs are kept as a reference field only; this
module never fetches or scrapes LinkedIn.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from . import compliance, db

# Our field -> header names seen in common exports (first match wins).
COLUMN_ALIASES: dict[str, list[str]] = {
    "first_name": ["First Name", "first_name", "Firstname", "Given Name"],
    "last_name": ["Last Name", "last_name", "Lastname", "Surname", "Family Name"],
    "email": ["Email", "email", "Work Email", "Email Address", "Business Email"],
    "title": ["Title", "Job Title", "title", "Position"],
    "company": ["Company", "Company Name", "Organisation", "Organization", "Account Name"],
    "domain": ["Website", "Company Domain", "Domain", "Company Website"],
    "industry": ["Industry", "industry"],
    "size": ["# Employees", "Employees", "Company Size"],
    "location": ["City", "Location", "Person City"],
    "country": ["Country", "Person Country"],
    "linkedin_url": ["Person Linkedin Url", "LinkedIn URL", "Linkedin", "linkedin_url"],
    "seniority": ["Seniority", "seniority"],
    "phone": ["Work Direct Phone", "Mobile Phone", "Phone", "Corporate Phone"],
    "headline": ["Headline", "headline"],
    "summary": ["Summary", "About", "Notes", "summary"],
    "skills": ["Skills", "Keywords", "skills"],
    "qualifications": ["Qualifications", "Certifications", "qualifications"],
    "work_preference": ["Work Preference", "Temp/Perm", "work_preference"],
    "email_status": ["Email Status"],
}


def _pick(row: dict, field: str) -> str:
    for h in COLUMN_ALIASES.get(field, [field]):
        if h in row and row[h] not in (None, ""):
            return str(row[h]).strip()
    return ""


def _domain_from(value: str) -> str:
    v = value.lower().strip()
    for p in ("https://", "http://", "www."):
        if v.startswith(p):
            v = v[len(p):]
    return v.split("/")[0]


def upsert_org(conn: sqlite3.Connection, name: str, domain: str, industry: str = "", size: str = "",
               location: str = "") -> str | None:
    if not name and not domain:
        return None
    domain = _domain_from(domain) if domain else ""
    if domain:
        row = conn.execute("SELECT id FROM organisations WHERE domain=?", (domain,)).fetchone()
        if row:
            return row["id"]
    else:
        row = conn.execute("SELECT id FROM organisations WHERE name=? AND domain IS NULL", (name,)).fetchone()
        if row:
            return row["id"]
    oid = db.new_id("org")
    conn.execute(
        "INSERT INTO organisations (id, name, domain, industry, size, location) VALUES (?,?,?,?,?,?)",
        (oid, name or domain, domain or None, industry, size, location),
    )
    return oid


def add_contact(conn: sqlite3.Connection, *, kind: str, brand_id: str, email: str, source: str,
                source_detail: str = "", lawful_basis: str = "legitimate_interests",
                consent_at: str | None = None, company: str = "", domain: str = "",
                industry: str = "", size: str = "", **fields) -> tuple[str, str]:
    """Insert or update a contact. Returns (contact_id, outcome)."""
    e = compliance.normalise_email(email)
    if not e or "@" not in e:
        return "", "skipped_no_email"
    if compliance.is_suppressed(conn, e):
        return "", "skipped_suppressed"
    if lawful_basis == "consent" and not consent_at:
        raise ValueError("lawful_basis=consent needs consent_at")

    org_id = upsert_org(conn, company, domain, industry, size, fields.get("location", ""))
    org_domain = None
    if org_id:
        r = conn.execute("SELECT domain FROM organisations WHERE id=?", (org_id,)).fetchone()
        org_domain = r["domain"]
    email_type = compliance.classify_email(e, org_domain)

    allowed = {"first_name", "last_name", "phone", "title", "location", "linkedin_url", "headline",
               "summary", "skills", "qualifications", "seniority", "work_preference"}
    data = {k: v for k, v in fields.items() if k in allowed and v}

    existing = conn.execute("SELECT id FROM contacts WHERE email=? AND brand_id=?", (e, brand_id)).fetchone()
    ts = db.now()
    if existing:
        sets = ", ".join(f"{k}=?" for k in data) + (", " if data else "")
        conn.execute(
            f"UPDATE contacts SET {sets} organisation_id=COALESCE(?, organisation_id), email_type=?, updated_at=? WHERE id=?",
            (*data.values(), org_id, email_type, ts, existing["id"]),
        )
        return existing["id"], "updated"

    cid = db.new_id("con")
    cols = ["id", "kind", "brand_id", "email", "email_type", "organisation_id", "source", "source_detail",
            "lawful_basis", "consent_at", "created_at", "updated_at", *data.keys()]
    vals = [cid, kind, brand_id, e, email_type, org_id, source, source_detail, lawful_basis, consent_at,
            ts, ts, *data.values()]
    conn.execute(f"INSERT INTO contacts ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
    return cid, "created"


def import_csv(conn: sqlite3.Connection, path: Path | str, *, kind: str, brand_id: str,
               source: str = "apollo_csv", source_detail: str = "a business contact database (Apollo.io)",
               actor: str = "import") -> dict:
    counts: dict[str, int] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            # Apollo marks unverifiable addresses; sending to them hurts deliverability.
            if _pick(row, "email_status").lower() in {"invalid", "unavailable", "bounced"}:
                counts["skipped_bad_email"] = counts.get("skipped_bad_email", 0) + 1
                continue
            location = ", ".join(x for x in (_pick(row, "location"), _pick(row, "country")) if x)
            _, outcome = add_contact(
                conn, kind=kind, brand_id=brand_id, email=_pick(row, "email"), source=source,
                source_detail=source_detail, company=_pick(row, "company"), domain=_pick(row, "domain"),
                industry=_pick(row, "industry"), size=_pick(row, "size"),
                first_name=_pick(row, "first_name"), last_name=_pick(row, "last_name"),
                title=_pick(row, "title"), location=location, linkedin_url=_pick(row, "linkedin_url"),
                seniority=_pick(row, "seniority"), phone=_pick(row, "phone"), headline=_pick(row, "headline"),
                summary=_pick(row, "summary"), skills=_pick(row, "skills"),
                qualifications=_pick(row, "qualifications"), work_preference=_pick(row, "work_preference"),
            )
            counts[outcome] = counts.get(outcome, 0) + 1
    db.audit(conn, actor, "import_csv", str(path), repr(counts))
    conn.commit()
    return counts
