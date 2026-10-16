"""Automatic prospecting: each morning, find new people who fit and add their work emails to the CRM.

Default route, no data provider in the middle (source = "companies_house"):

1. Companies House advanced search for active companies in the area and
   industries in `prospecting.toml`, moving on from where yesterday stopped.
2. Size check from the latest accounts filed (micro/small/medium/large).
3. Officers from the register whose stated occupation matches a target title
   (e.g. "Finance Director", "Chartered Accountant").
4. The company's own website (found and confirmed by `website.find_site`):
   names beside matching job titles on team/about pages, and any published
   work addresses.
5. A work email for each person (`emailfind.find`): published on the site,
   accepted by their mail server, or built from the company's own format.
   Only the statuses listed in `email.accept` are used.
6. Optional paid fallback (Hunter or Apollo) for people step 5 couldn't
   confirm, inside a daily credit cap.
7. `importers.add_contact` then the usual checks: suppression list, corporate
   address only (PECR), and each contact records where the details came from
   for the first email's privacy line (UK GDPR Article 14).

Alternative route (source = "apollo"): Apollo's People Search (free of
credits) plus one credit per email revealed, inside the same caps.

Never touches LinkedIn. Limited companies, PLCs and LLPs only: they are
corporate subscribers under PECR, unlike sole traders and partnerships.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import compliance, db, emailfind, importers, lookup, net, website
from .companies_house import CompaniesHouse, size_of
from .settings import Settings

DIY_SOURCE = "the public Companies House register and {company}'s own website"


@dataclass
class Config:
    brand: str = "finance"
    source: str = "companies_house"            # or "apollo"
    location: str = ""
    sizes: list[str] = field(default_factory=lambda: ["small", "medium"])
    sic_codes: list[str] = field(default_factory=list)
    exclude_sic_codes: list[str] = field(default_factory=list)
    company_types: list[str] = field(default_factory=lambda: ["ltd", "plc", "llp"])
    min_age_years: int = 2
    client_titles: list[str] = field(default_factory=lambda: [
        "chief financial officer", "cfo", "finance director", "financial director", "head of finance",
        "financial controller", "finance manager"])
    candidate_titles: list[str] = field(default_factory=list)
    exclude_titles: list[str] = field(default_factory=lambda: ["non-executive", "trainee", "apprentice"])
    max_per_company: int = 2
    accept: list[str] = field(default_factory=lambda: ["published", "verified", "pattern"])
    smtp_check: bool = True
    companies_per_day: int = 40
    new_contacts_per_day: int = 25
    smtp_checks_per_day: int = 60
    seconds_between_requests: float = 3.0
    pages_per_site: int = 6
    fallback: str = "none"                     # "hunter" or "apollo"
    credits_per_day: int = 5
    apollo_locations: list[str] = field(default_factory=list)
    apollo_employee_ranges: list[str] = field(default_factory=lambda: ["11,50", "51,200"])

    @property
    def titles(self) -> list[str]:
        return self.client_titles + self.candidate_titles

    def search_key(self) -> str:
        raw = json.dumps([self.source, self.location.lower(), sorted(self.sic_codes), sorted(self.company_types),
                          self.min_age_years, self.apollo_locations, self.apollo_employee_ranges, self.titles])
        return hashlib.sha1(raw.encode()).hexdigest()[:16]


def load_config(path: Path | str) -> Config:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    flat: dict = {k: v for k, v in data.items() if not isinstance(v, dict)}
    for section in data.values():
        if isinstance(section, dict):
            flat.update(section)
    known = Config.__dataclass_fields__
    unknown = sorted(set(flat) - set(known))
    if unknown:
        raise ValueError(f"unknown setting(s) in {path}: {', '.join(unknown)}")
    cfg = Config(**flat)
    bad = set(cfg.sizes) - {"micro", "small", "medium", "large"}
    if bad:
        raise ValueError(f"sizes must be micro, small, medium or large, not {sorted(bad)}")
    if cfg.source not in ("companies_house", "apollo"):
        raise ValueError("source must be companies_house or apollo")
    if cfg.source == "companies_house" and not cfg.location.strip():
        raise ValueError(f"set location in {path} (your town, city or county) to start prospecting")
    return cfg


# -- bookkeeping --------------------------------------------------------------

def _used(conn, day: str, what: str) -> int:
    r = conn.execute("SELECT n FROM prospect_usage WHERE day=? AND what=?", (day, what)).fetchone()
    return r["n"] if r else 0


def _bump(conn, day: str, what: str, n: int = 1) -> None:
    conn.execute("INSERT INTO prospect_usage (day, what, n) VALUES (?,?,?)"
                 " ON CONFLICT(day, what) DO UPDATE SET n = n + excluded.n", (day, what, n))


def _cursor(conn, key: str) -> int:
    r = conn.execute("SELECT next_index FROM prospect_cursor WHERE search_key=?", (key,)).fetchone()
    return r["next_index"] if r else 0


def _save_cursor(conn, key: str, index: int, total: int | None) -> None:
    conn.execute("INSERT INTO prospect_cursor (search_key, next_index, total, updated_at) VALUES (?,?,?,?)"
                 " ON CONFLICT(search_key) DO UPDATE SET next_index=excluded.next_index, total=excluded.total,"
                 " updated_at=excluded.updated_at", (key, index, total, db.now()))


def _title_match(text: str, titles: list[str]) -> str:
    return website._title_hit(text or "", titles)


def _already_known(conn, number: str, first: str, last: str, domain: str) -> str:
    if conn.execute("SELECT 1 FROM prospect_people WHERE company_number=? AND lower(first_name)=? AND"
                    " lower(last_name)=?", (number, first.lower(), last.lower())).fetchone():
        return "seen_before"
    if domain and conn.execute(
            "SELECT 1 FROM contacts c JOIN organisations o ON o.id=c.organisation_id WHERE o.domain=?"
            " AND lower(c.first_name)=? AND lower(c.last_name)=?", (domain, first.lower(), last.lower())).fetchone():
        return "already_in_crm"
    return ""


def _record_person(conn, number, p, outcome, email=None, status=None, contact_id=None, pid=None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO prospect_people (id, company_number, first_name, last_name, title, found_via,"
        " evidence_url, email, email_status, contact_id, outcome, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (pid or db.new_id("pp"), number, p["first_name"], p["last_name"], p.get("title"), p["via"],
         p.get("evidence_url"), email, status, contact_id, outcome, db.now()))


def _record_company(conn, number, name, domain, size, location, outcome, people) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO prospect_companies (company_number, name, domain, size, location, outcome,"
        " people_found, checked_at) VALUES (?,?,?,?,?,?,?,?)",
        (number, name, domain, size, location, outcome, people, db.now()))


class _Run:
    def __init__(self, conn, settings, cfg, day, prober, fallback):
        self.conn, self.settings, self.cfg, self.day = conn, settings, cfg, day
        self.prober, self.fallback = prober, fallback
        self.counts: Counter = Counter()
        self.added: list[dict] = []
        self.room = cfg.new_contacts_per_day - _used(conn, day, "contacts")
        self.credits = cfg.credits_per_day - _used(conn, day, "credits")
        self.dry_run = False
        self.note = ""

    def add(self, p: dict, found: lookup.Found | None, *, number: str, company: str, domain: str, size: str = "",
            location: str = "", pid: str | None = None, status: str | None = None) -> str:
        """Run the compliance checks, add the contact, record the outcome. Returns the outcome."""
        ok, reason = lookup.check(found, domain or None)
        if found is None and status:
            reason = f"unverified_{status}"      # we have a likely address, just not a sure enough one
        cid = None
        if ok:
            cid, outcome = importers.add_contact(
                self.conn, kind=p["kind"], brand_id=self.cfg.brand, email=found.email,
                source=f"prospect_{found.provider}", source_detail=found.source_detail, company=company,
                domain=domain, size=size, first_name=p["first_name"], last_name=p["last_name"],
                title=p.get("title"), location=location)
            if outcome == "created":
                c = self.conn.execute("SELECT * FROM contacts WHERE id=?", (cid,)).fetchone()
                allowed, why = compliance.can_email(self.conn, c)
                reason = "added" if allowed else why
                where = p.get("evidence_url") or "the Companies House register"
                self.conn.execute(
                    "INSERT INTO notes (id, contact_id, author, body, created_at) VALUES (?,?,?,?,?)",
                    (db.new_id("note"), cid, "prospecting",
                     f"Found automatically: {p.get('title') or 'finance'} at {company} ({where}). "
                     f"Email {found.status} via {found.provider}.", db.now()))
                if allowed:
                    self.room -= 1
                    _bump(self.conn, self.day, "contacts")
                    self.added.append({"name": f"{p['first_name']} {p['last_name']}", "title": p.get("title"),
                                       "company": company, "email": found.email, "status": found.status})
            else:
                reason = "already_in_crm" if outcome == "updated" else outcome
        self.counts[reason] += 1
        _record_person(self.conn, number, p, reason, found.email if found else None,
                       status or (found.status if found else "none"), cid if reason == "added" else None, pid)
        return reason

    def paid_fallback(self, p: dict, company: str, domain: str) -> lookup.Found | None:
        if self.fallback is None or self.credits <= 0:
            return None
        self.credits -= 1
        _bump(self.conn, self.day, "credits")
        self.counts["fallback_lookups"] += 1
        try:
            return self.fallback.find(p["first_name"], p["last_name"], company, domain, None)
        except Exception as exc:  # noqa: BLE001  quota or network: carry on without it
            db.audit(self.conn, "prospecting", "fallback_failed", company, str(exc)[:200])
            return None


def _people_for(cfg: Config, officers: list[dict], site: website.Site | None) -> list[dict]:
    people: list[dict] = []
    for o in officers:
        hit = _title_match(o["occupation"], cfg.titles)
        if hit:
            people.append({"first_name": o["first_name"], "last_name": o["last_name"], "kind": "client",
                           "title": o["occupation"].title(), "matched": hit, "via": "companies_house",
                           "evidence_url": None})
    for page in (site.pages if site else []):
        for p in website.people_on(page, cfg.titles):
            p["kind"] = "client" if _title_match(p["title"], cfg.client_titles) else "candidate"
            p["via"] = "website"
            people.append(p)
    seen, out = set(), []
    for p in people:
        k = (p["first_name"].lower(), p["last_name"].lower())
        if k in seen or _title_match(p["title"], cfg.exclude_titles):
            continue
        seen.add(k)
        out.append(p)
    rank = {t: i for i, t in enumerate(cfg.titles)}
    out.sort(key=lambda p: rank.get(p["matched"], 99))
    return out[: cfg.max_per_company]


def _company(run: _Run, item: dict, ch: CompaniesHouse, polite: net.Polite, dns_get) -> bool:
    """Check one company. False if today's contact cap ran out part-way (it's finished next run)."""
    cfg, conn = run.cfg, run.conn
    number, name = item["company_number"], item.get("company_name") or item.get("title") or ""
    addr = item.get("registered_office_address") or {}
    postcode, town = addr.get("postal_code") or "", addr.get("locality") or ""
    if set(item.get("sic_codes") or []) & set(cfg.exclude_sic_codes):
        run.counts["excluded_industry"] += 1
        _record_company(conn, number, name, None, None, town, "excluded_industry", 0)
        return True
    size = size_of(ch.profile(number))
    if size not in cfg.sizes:
        run.counts["wrong_size"] += 1
        _record_company(conn, number, name, None, size, town, "wrong_size", 0)
        return True
    officers = ch.officers(number)
    site = website.find_site(polite, name, number, postcode, max_pages=cfg.pages_per_site)
    people = _people_for(cfg, officers, site)
    domain = site.domain if site else None
    if not people:
        run.counts["no_people"] += 1
        _record_company(conn, number, name, domain, size, town, "no_site" if not site else "no_people", 0)
        return True
    if not site:
        run.counts["no_website"] += 1
        for p in people:
            _record_person(conn, number, p, "no_website")
        _record_company(conn, number, name, None, size, town, "no_site", len(people))
        return True
    mx = emailfind.mx_hosts(site.domain, dns_get)
    anchors = [(o["first_name"], o["last_name"]) for o in officers] + [(p["first_name"], p["last_name"])
                                                                      for p in people]
    detail = DIY_SOURCE.format(company=name.title() if name.isupper() else name)
    for p in people:
        if run.room <= 0:
            return False
        known = _already_known(conn, number, p["first_name"], p["last_name"], site.domain)
        if known:
            run.counts[known] += 1
            continue
        g = emailfind.find(p["first_name"], p["last_name"], site.domain, site.emails, anchors, mx, run.prober)
        found = None
        if g and g.status in cfg.accept:
            found = lookup.Found(g.email, True, g.status, "diy", detail, site.domain)
        elif mx:
            found = run.paid_fallback(p, name, site.domain)
        run.add(p, found, number=number, company=name, domain=site.domain, size=size, location=town,
                status=g.status if g and found is None else None)
    _record_company(conn, number, name, site.domain, size, town, "checked", len(people))
    return True


def _run_companies_house(run: _Run, ch, polite, dns_get, today: date) -> None:
    cfg, conn = run.cfg, run.conn
    key = cfg.search_key()
    index = _cursor(conn, key)
    budget = cfg.companies_per_day - _used(conn, run.day, "companies")
    total = None
    while budget > 0 and run.room > 0:
        items, total = ch.search(location=cfg.location, sic_codes=cfg.sic_codes, company_types=cfg.company_types,
                                 min_age_years=cfg.min_age_years, start_index=index, size=50, today=today)
        if not items:
            run.counts["search_finished"] += 1
            break
        for item in items:
            if budget <= 0 or run.room <= 0:
                break
            index += 1
            if conn.execute("SELECT 1 FROM prospect_companies WHERE company_number=?",
                            (item["company_number"],)).fetchone():
                run.counts["company_seen_before"] += 1
                continue
            budget -= 1
            _bump(conn, run.day, "companies")
            run.counts["companies_checked"] += 1
            if not _company(run, item, ch, polite, dns_get):
                index -= 1                # come back to the rest of this company tomorrow
                break
            _save_cursor(conn, key, index, total)
            if not run.dry_run:
                conn.commit()             # a crash later keeps the work done so far
        _save_cursor(conn, key, index, total)
        if total is not None and index >= total:
            run.counts["search_finished"] += 1
            break


def _run_apollo(run: _Run, apollo: lookup.ApolloSearch) -> None:
    cfg, conn = run.cfg, run.conn
    key = cfg.search_key()
    page = _cursor(conn, key) or 1
    locations = cfg.apollo_locations or ([f"{cfg.location}, United Kingdom"] if cfg.location else ["United Kingdom"])
    while run.room > 0 and run.credits > 0:
        people = apollo.search(cfg.titles, locations, cfg.apollo_employee_ranges, page)
        if not people:
            run.counts["search_finished"] += 1
            break
        for person in people:
            if run.room <= 0 or run.credits <= 0:
                break
            pid = f"pp_apollo_{person.get('id')}"
            if conn.execute("SELECT 1 FROM prospect_people WHERE id=?", (pid,)).fetchone():
                run.counts["seen_before"] += 1
                continue
            run.credits -= 1
            _bump(conn, run.day, "credits")
            try:
                full = apollo.reveal(person["id"])
            except Exception as exc:  # noqa: BLE001
                db.audit(conn, "prospecting", "apollo_reveal_failed", pid, str(exc)[:200])
                run.counts["error"] += 1
                continue
            org = full.get("organization") or person.get("organization") or {}
            title = full.get("title") or person.get("title") or ""
            p = {"first_name": full.get("first_name") or person.get("first_name") or "",
                 "last_name": full.get("last_name") or "", "title": title, "via": "apollo",
                 "kind": "client" if _title_match(title, cfg.client_titles) else "candidate", "evidence_url": None}
            if not p["first_name"] or not p["last_name"]:
                run.counts["incomplete"] += 1
                continue
            status = full.get("email_status") or "unknown"
            found = lookup.Found(full["email"], status == "verified", status, "apollo",
                                 lookup.Apollo.source_detail, org.get("primary_domain") or "") if full.get("email") else None
            number = f"apollo:{org.get('id') or org.get('name') or '-'}"
            run.add(p, found, number=number, company=org.get("name") or "", domain=org.get("primary_domain") or "",
                    location=full.get("city") or "", pid=pid)
        page += 1
        _save_cursor(conn, key, page, None)


def run(conn: sqlite3.Connection, settings: Settings, cfg: Config, *, ch=None, polite=None, dns_get=None,
        prober=None, fallback=None, apollo=None, dry_run: bool = False, now: datetime | None = None) -> dict:
    """Find today's new people. Safe to re-run: daily caps are counted across runs."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo(settings.timezone)).date()
    day = today.isoformat()
    conn.commit()
    brand = conn.execute("SELECT * FROM brands WHERE id=?", (cfg.brand,)).fetchone()
    if brand is None:
        raise ValueError(f"unknown brand {cfg.brand!r}")
    if fallback is None and cfg.fallback != "none":
        fallback = lookup.provider_from_settings(dataclasses.replace(settings, email_provider=cfg.fallback))
    if cfg.smtp_check and prober is None and cfg.source == "companies_house":
        mail_from = settings.recruiter_email
        prober = emailfind.SmtpProber(helo=mail_from.rpartition("@")[2], mail_from=mail_from,
                                      budget=cfg.smtp_checks_per_day - _used(conn, day, "smtp"))
    r = _Run(conn, settings, cfg, day, prober, fallback)
    r.dry_run = dry_run
    if cfg.source == "apollo":
        if apollo is None:
            if not settings.apollo_api_key:
                raise RuntimeError("Set APOLLO_API_KEY to prospect with Apollo.")
            apollo = lookup.ApolloSearch(settings.apollo_api_key)
        _run_apollo(r, apollo)
    else:
        if ch is None:
            if not settings.companies_house_api_key:
                raise RuntimeError("Set COMPANIES_HOUSE_API_KEY (free from developer.company-information."
                                   "service.gov.uk) to prospect with Companies House.")
            ch = CompaniesHouse(settings.companies_house_api_key)
        polite = polite or net.Polite(f"WrenfieldProspector/1.0 (+{brand['website']}; {settings.recruiter_email})",
                                      gap=cfg.seconds_between_requests)
        try:
            _run_companies_house(r, ch, polite, dns_get or net.http_get, today)
        except RuntimeError as exc:          # Companies House key or rate limit: keep what we have
            r.counts["stopped_early"] += 1
            r.note = str(exc)
            db.audit(conn, "prospecting", "stopped", "", str(exc)[:200])
        if prober is not None:
            _bump(conn, day, "smtp", prober.used)
            if prober.disabled:
                r.counts["smtp_check_unavailable"] += 1
    db.audit(conn, "prospecting", "run", cfg.search_key(), json.dumps(dict(r.counts)))
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {"counts": dict(r.counts), "added": r.added, "dry_run": dry_run, "note": r.note}


def run_from_settings(conn: sqlite3.Connection, settings: Settings, **kw) -> dict:
    """What `crm daily` calls: skips quietly when there's no config file."""
    path = Path(settings.prospect_config)
    if not path.exists():
        return {"skipped": f"no {path}"}
    try:
        return run(conn, settings, load_config(path), **kw)
    except (RuntimeError, ValueError) as exc:
        return {"error": str(exc)}


def summary(result: dict) -> list[str]:
    if "skipped" in result or "error" in result:
        return [f"Prospecting: {result.get('error') or result.get('skipped')}"]
    c = result["counts"]
    lines = [f"Prospecting{' (dry run, nothing saved)' if result.get('dry_run') else ''}: "
             f"checked {c.get('companies_checked', 0)} companies, added {len(result['added'])} people."]
    if result.get("note"):
        lines.append(f"Stopped early: {result['note']}")
    for a in result["added"]:
        lines.append(f"- {a['name']}, {a['title'] or '-'} at {a['company']}: {a['email']} ({a['status']})")
    skipped = {k: v for k, v in c.items() if k not in ("companies_checked", "added")}
    if skipped:
        lines.append("Other outcomes: " + ", ".join(f"{k} {v}" for k, v in sorted(skipped.items())))
    return lines
