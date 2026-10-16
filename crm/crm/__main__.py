"""Command line: python -m crm <command> ...

Lean launch (one person, hand-sent email), each weekday morning:
  python -m crm targets today.txt --brand finance --kind client   # people you noted on LinkedIn / Apollo
  python -m crm daily --out today.md                              # find emails, check, draft ~20, LinkedIn notes
  ...send them from your mailbox...
  python -m crm sent                                              # log what you sent
  python -m crm li invited <id> <id>                              # log LinkedIn invitations

Typical day with AI assistants sending, from cron:
  */5 8-18 * * 1-5  python -m crm tick         # draft due steps, send within caps
  30 7 * * 1-5      python -m crm standup      # morning brief for Tristan
  0 3 * * 0         python -m crm purge        # retention clean-up
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import booking, compliance, daily, db, engine, importers, standup, web
from .personalise import Writer
from .settings import load


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="crm")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create the database and default brands")

    a = sub.add_parser("add-assistant")
    a.add_argument("id"); a.add_argument("display_name"); a.add_argument("mailbox"); a.add_argument("calendly_url")
    a.add_argument("--brand"); a.add_argument("--started-on")
    a.add_argument("--human", action="store_true", help="a person sending under their own name (no AI disclosure)")

    s = sub.add_parser("load-sequences"); s.add_argument("paths", nargs="+")

    i = sub.add_parser("import", help="import a CSV export (Apollo or similar)")
    i.add_argument("csv"); i.add_argument("--kind", required=True, choices=["candidate", "client"])
    i.add_argument("--brand", required=True); i.add_argument("--source", default="apollo_csv")
    i.add_argument("--source-detail", default="a business contact database (Apollo.io)")

    c = sub.add_parser("add-contact", help="add one contact by hand")
    c.add_argument("--kind", required=True, choices=["candidate", "client"]); c.add_argument("--brand", required=True)
    c.add_argument("--email", required=True); c.add_argument("--first-name"); c.add_argument("--last-name")
    c.add_argument("--title"); c.add_argument("--company"); c.add_argument("--domain"); c.add_argument("--skills")
    c.add_argument("--summary"); c.add_argument("--linkedin-url"); c.add_argument("--consent-at",
        help="ISO timestamp the person opted in (e.g. website form). Sets lawful basis to consent.")

    n = sub.add_parser("note"); n.add_argument("email"); n.add_argument("text")

    e = sub.add_parser("enroll"); e.add_argument("sequence"); e.add_argument("assistant")
    e.add_argument("--brand"); e.add_argument("--kind"); e.add_argument("--status", default="new")
    e.add_argument("--limit", type=int, default=100)

    t = sub.add_parser("targets", help="add people to the LinkedIn/email list (CSV export or 'name | title | company | url' lines)")
    t.add_argument("path"); t.add_argument("--brand", default="finance")
    t.add_argument("--kind", default="client", choices=["candidate", "client"]); t.add_argument("--source")
    sub.add_parser("find-emails", help="look up work emails with the configured provider (Apollo or Hunter)")
    d = sub.add_parser("daily", help="prepare today's emails and LinkedIn invitations")
    d.add_argument("--sender", default="tristan"); d.add_argument("--brand", default="finance")
    d.add_argument("--out", help="also write the list to this Markdown file")
    hs = sub.add_parser("sent", help="log emails you sent by hand from the daily list")
    hs.add_argument("ids", nargs="*", help="message ids, or none for all on the list")
    li = sub.add_parser("li", help="log what you did on LinkedIn")
    li.add_argument("event", choices=sorted(daily.LI_EVENTS)); li.add_argument("ids", nargs="+")

    sub.add_parser("tick", help="draft due steps and send what the caps allow")
    sub.add_parser("review", help="show drafts waiting for approval")
    ap = sub.add_parser("approve"); ap.add_argument("ids", nargs="*", help="message ids, or none for all")

    r = sub.add_parser("reply", help="record an inbound reply"); r.add_argument("from_email")
    r.add_argument("subject"); r.add_argument("body")
    b = sub.add_parser("bounce"); b.add_argument("email")
    u = sub.add_parser("unsubscribe"); u.add_argument("email")
    er = sub.add_parser("erase", help="right to erasure"); er.add_argument("email")
    ex = sub.add_parser("export", help="subject access export"); ex.add_argument("email")
    sub.add_parser("purge", help="delete contacts past the retention period")

    st = sub.add_parser("standup"); st.add_argument("--out", help="write Markdown here as well")
    cw = sub.add_parser("calendly-sim", help="simulate a Calendly booking")
    cw.add_argument("email"); cw.add_argument("assistant"); cw.add_argument("start"); cw.add_argument("end")

    sv = sub.add_parser("serve"); sv.add_argument("--port", type=int, default=8080)

    args = p.parse_args(argv)
    settings = load()
    conn = db.connect(settings.db_path)
    if args.cmd != "init":
        db.init(conn, settings.public_base_url)  # idempotent; keeps commands safe to run on a fresh DB

    if args.cmd == "init":
        db.init(conn, settings.public_base_url); print(f"initialised {settings.db_path}")
    elif args.cmd == "add-assistant":
        engine.add_assistant(conn, args.id, args.display_name, args.mailbox, args.calendly_url, args.brand,
                             args.started_on, is_ai=not args.human)
    elif args.cmd == "load-sequences":
        for path in args.paths:
            print("loaded", engine.load_sequence(conn, path))
    elif args.cmd == "import":
        print(importers.import_csv(conn, args.csv, kind=args.kind, brand_id=args.brand, source=args.source,
                                   source_detail=args.source_detail))
    elif args.cmd == "add-contact":
        cid, outcome = importers.add_contact(
            conn, kind=args.kind, brand_id=args.brand, email=args.email, source="manual",
            source_detail="details you shared with us or that are publicly listed for your work",
            lawful_basis="consent" if args.consent_at else "legitimate_interests", consent_at=args.consent_at,
            company=args.company or "", domain=args.domain or "", first_name=args.first_name,
            last_name=args.last_name, title=args.title, skills=args.skills, summary=args.summary,
            linkedin_url=args.linkedin_url)
        conn.commit(); print(cid, outcome)
    elif args.cmd == "note":
        rows = conn.execute("SELECT id FROM contacts WHERE email=?", (compliance.normalise_email(args.email),)).fetchall()
        for row in rows:
            conn.execute("INSERT INTO notes (id, contact_id, author, body, created_at) VALUES (?,?,?,?,?)",
                         (db.new_id("note"), row["id"], "tristan", args.text, db.now()))
        conn.commit(); print(f"noted on {len(rows)} record(s)")
    elif args.cmd == "enroll":
        q = "SELECT id FROM contacts WHERE status=?"
        params: list = [args.status]
        if args.brand: q += " AND brand_id=?"; params.append(args.brand)
        if args.kind: q += " AND kind=?"; params.append(args.kind)
        results: dict[str, int] = {}
        for row in conn.execute(q + " LIMIT ?", (*params, args.limit)).fetchall():
            _, outcome = engine.enroll(conn, row["id"], args.sequence, args.assistant)
            results[outcome] = results.get(outcome, 0) + 1
        print(results)
    elif args.cmd == "targets":
        print(daily.import_targets(conn, args.path, brand_id=args.brand, kind=args.kind, source=args.source))
    elif args.cmd == "find-emails":
        print(daily.find_emails(conn, settings))
    elif args.cmd == "daily":
        print(json.dumps(daily.build(conn, settings, args.sender, args.brand)))
        md = daily.render(conn, settings, args.sender)
        if args.out:
            Path(args.out).write_text(md)
        print(md)
    elif args.cmd == "sent":
        print(engine.mark_sent(conn, settings, args.ids or None))
    elif args.cmd == "li":
        print("updated", daily.log_linkedin(conn, args.ids, args.event))
    elif args.cmd == "tick":
        print(json.dumps(engine.tick(conn, settings), indent=1))
    elif args.cmd == "review":
        for m in conn.execute("SELECT m.id, c.email, m.subject, m.body FROM messages m JOIN contacts c"
                              " ON c.id=m.contact_id WHERE m.status='draft' ORDER BY m.created_at"):
            print(f"=== {m['id']} -> {m['email']}\nSubject: {m['subject']}\n\n{m['body']}\n")
    elif args.cmd == "approve":
        print("approved", engine.approve(conn, args.ids or None))
    elif args.cmd == "reply":
        print(engine.record_reply(conn, settings, args.from_email, args.subject, args.body))
    elif args.cmd == "bounce":
        engine.record_bounce(conn, args.email); print("suppressed")
    elif args.cmd == "unsubscribe":
        compliance.suppress(conn, args.email, "manual", actor="tristan"); conn.commit(); print("suppressed")
    elif args.cmd == "erase":
        print("erased", compliance.erase(conn, args.email, actor="tristan"), "record(s)")
    elif args.cmd == "export":
        print(json.dumps(compliance.subject_access_export(conn, args.email), indent=1, default=str))
    elif args.cmd == "purge":
        print("purged", compliance.purge_stale(conn, settings.retention_days))
    elif args.cmd == "standup":
        md = standup.build(conn, settings, writer=Writer(settings))
        if args.out:
            Path(args.out).write_text(md)
        print(md)
    elif args.cmd == "calendly-sim":
        c = conn.execute("SELECT * FROM contacts WHERE email=?", (compliance.normalise_email(args.email),)).fetchone()
        print(booking.handle_webhook(conn, settings, booking.sample_event(c, args.assistant, args.start, args.end,
                                                                         email=args.email), settings.outbox_dir))
    elif args.cmd == "serve":
        web.serve(settings, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
