"""Daily list: targets in, compliant email lookup, ~20 hand-sent emails, LinkedIn notes."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crm import daily, db, engine, lookup  # noqa: E402
from crm.personalise import Writer  # noqa: E402
from crm.settings import Settings  # noqa: E402

T0 = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)  # Tuesday


class FakeProvider:
    name = "apollo"

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def find(self, first_name, last_name, company, domain, profile_url):
        self.calls.append(first_name)
        a = self.answers.get(first_name)
        if a is None:
            return None
        email, verified = a
        return lookup.Found(email, verified, "verified" if verified else "guessed", "apollo",
                            lookup.Apollo.source_detail, email.rpartition("@")[2])


LIST = """# name | title | company | profile | domain | why
Jane Smith | Financial Controller | Acme Ltd | linkedin.com/in/janesmith/ | acme.example | new FD joined in May
Raj Patel | Finance Director | Brook Foods | https://uk.linkedin.com/in/rajpatel?trk=x | brookfoods.example |
Amy Lee | Head of Finance | Cole & Co | https://www.linkedin.com/in/amylee | coleco.example |
Ben Ford | CFO | Ford Group | https://www.linkedin.com/in/benford | fordgroup.example |
Jane Smith again | | | https://www.linkedin.com/in/janesmith |
No Url Person | FD | Nowhere Ltd
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.s = Settings()
        self.s.db_path, self.s.outbox_dir, self.s.llm = self.tmp / "t.db", self.tmp / "outbox", "offline"
        self.s.unsub_mode = "reply"
        self.s.prospect_config = self.tmp / "no-prospecting.toml"
        self.conn = db.connect(self.s.db_path)
        db.init(self.conn)
        engine.add_assistant(self.conn, "tristan", "Tristan", "tristan@wrenfieldfinance.example",
                             "https://calendly.com/example-tristan/intro", brand_id="finance", is_ai=False)
        for f in (ROOT / "sequences").glob("*.json"):
            engine.load_sequence(self.conn, f)
        p = self.tmp / "today.txt"
        p.write_text(LIST)
        self.counts = daily.import_targets(self.conn, p, brand_id="finance", kind="client")
        self.provider = FakeProvider({
            "Jane": ("jane.smith@acme.example", True),
            "Raj": ("raj@gmail.com", True),               # personal: PECR says no
            "Amy": ("amy.lee@coleco.example", False),     # unverified: bounce risk
            "Ben": ("ben@someoneelse.example", True),     # not the company's domain
        })

    def tearDown(self):
        self.conn.close()


class Targets(Base):
    def test_import_dedupes_and_needs_url(self):
        self.assertEqual(self.counts, {"added": 4, "duplicate": 1, "skipped_needs_name_and_url": 1})
        urls = [r[0] for r in self.conn.execute("SELECT profile_url FROM linkedin_targets ORDER BY profile_url")]
        self.assertIn("https://www.linkedin.com/in/rajpatel", urls)
        self.assertIn("https://www.linkedin.com/in/janesmith", urls)

    def test_lookup_keeps_only_verified_work_addresses(self):
        counts = daily.find_emails(self.conn, self.s, self.provider)
        self.assertEqual(counts, {"ok": 1, "personal_address": 1, "unverified_guessed": 1, "not_company_domain": 1})
        c = self.conn.execute("SELECT * FROM contacts").fetchall()
        self.assertEqual([r["email"] for r in c], ["jane.smith@acme.example"])
        self.assertEqual(c[0]["email_type"], "corporate")
        self.assertEqual(c[0]["source"], "apollo_lookup")
        note = self.conn.execute("SELECT body FROM notes").fetchone()["body"]
        self.assertEqual(note, "new FD joined in May")
        # Already looked up: not charged twice.
        self.assertEqual(daily.find_emails(self.conn, self.s, self.provider), {})

    def test_no_provider_means_no_network(self):
        self.assertEqual(daily.find_emails(self.conn, self.s), {"skipped_no_provider": 1})

    def test_personal_mailbox_refused_as_sender(self):
        with self.assertRaises(ValueError):
            engine.add_assistant(self.conn, "x", "Tristan", "tristan@gmail.com", "https://calendly.com/x")


class DailyList(Base):
    def test_build_render_and_mark_sent(self):
        res = daily.build(self.conn, self.s, "tristan", "finance", Writer(self.s), self.provider, now=T0)
        self.assertEqual(res["emails"], 1)
        self.assertEqual(res["linkedin"], 4)
        md = daily.render(self.conn, self.s, "tristan", now=T0)
        self.assertIn("To: jane.smith@acme.example", md)
        self.assertIn("mailto:jane.smith%40acme.example", md)
        self.assertIn('reply "unsubscribe"', md)
        self.assertIn("Apollo.io", md)                 # Art. 14 source line in the first email
        self.assertNotIn("AI assistant", md)           # a person sending as themselves
        # People with no usable email come first on the LinkedIn list.
        li = md.split("## LinkedIn invitations")[1]
        self.assertLess(li.index("Raj"), li.index("Jane"))
        for t in self.conn.execute("SELECT * FROM linkedin_targets"):
            self.assertLessEqual(len(t["note_draft"]), 200)
            self.assertNotIn("http", t["note_draft"])

        # The engine never sends a person's mail for them.
        self.assertEqual(engine.send_due(self.conn, self.s, now=T0), {})
        self.assertEqual(engine.mark_sent(self.conn, self.s, now=T0), {"sent": 1})
        c = self.conn.execute("SELECT * FROM contacts").fetchone()
        self.assertEqual(c["status"], "contacted")
        self.assertIsNotNone(c["art14_notice_sent_at"])
        e = self.conn.execute("SELECT * FROM enrollments").fetchone()
        self.assertEqual(e["current_step"], 1)

        # Follow-up comes back onto the list when it's due, and the Art. 14 line isn't repeated.
        daily.build(self.conn, self.s, "tristan", "finance", Writer(self.s), self.provider, now=T0 + timedelta(days=4))
        md2 = daily.render(self.conn, self.s, "tristan", now=T0 + timedelta(days=4))
        self.assertIn("(follow-up 1)", md2)
        self.assertNotIn("Apollo.io", md2.split("## LinkedIn")[0])

    def test_daily_email_cap(self):
        self.s.daily_emails = 3
        for i in range(6):
            daily.add_target(self.conn, brand_id="finance", kind="client", first_name=f"P{i}", last_name="X",
                             company=f"Co{i}", company_domain=f"co{i}.example",
                             profile_url=f"https://www.linkedin.com/in/p{i}")
        self.provider.answers.update({f"P{i}": (f"p{i}@co{i}.example", True) for i in range(6)})
        res = daily.build(self.conn, self.s, "tristan", "finance", Writer(self.s), self.provider, now=T0)
        self.assertEqual(res["emails"], 3)
        # Re-running tops up, never duplicates.
        res = daily.build(self.conn, self.s, "tristan", "finance", Writer(self.s), self.provider, now=T0)
        self.assertEqual(res["emails"], 3)

    def test_linkedin_weekly_cap_and_logging(self):
        self.s.linkedin_daily, self.s.linkedin_weekly = 3, 4
        daily.build(self.conn, self.s, "tristan", "finance", Writer(self.s), now=T0)
        listed = [r["id"] for r in self.conn.execute("SELECT id FROM linkedin_targets WHERE status='listed'")]
        self.assertEqual(len(listed), 3)
        daily.log_linkedin(self.conn, listed, "invited")
        for i in range(3):
            daily.add_target(self.conn, brand_id="finance", kind="client", first_name=f"Q{i}",
                             profile_url=f"https://www.linkedin.com/in/q{i}")
        daily.build(self.conn, self.s, "tristan", "finance", Writer(self.s), now=T0 + timedelta(days=1))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM linkedin_targets WHERE status='listed'").fetchone()[0], 1)

    def test_suppressed_person_never_listed(self):
        from crm import compliance
        compliance.suppress(self.conn, "jane.smith@acme.example", "unsubscribe")
        res = daily.build(self.conn, self.s, "tristan", "finance", Writer(self.s), self.provider, now=T0)
        self.assertEqual(res["emails"], 0)


class Providers(unittest.TestCase):
    def test_apollo_request(self):
        seen = {}

        def fetch(req):
            seen["url"], seen["headers"], seen["body"] = req.full_url, dict(req.header_items()), json.loads(req.data)
            return {"person": {"email": "a@acme.example", "email_status": "verified",
                               "organization": {"primary_domain": "acme.example"}}}
        f = lookup.Apollo("k", fetch).find("Ann", "Bee", "Acme", "", "https://www.linkedin.com/in/ann")
        self.assertEqual(seen["url"], "https://api.apollo.io/api/v1/people/match")
        self.assertEqual(seen["headers"]["X-api-key"], "k")
        self.assertFalse(seen["body"]["reveal_personal_emails"])
        self.assertTrue(f.verified)
        self.assertEqual(lookup.check(f, None), (True, "ok"))

    def test_hunter_request(self):
        def fetch(req):
            self.assertIn("domain=acme.example", req.full_url)
            return {"data": {"email": "ann@acme.example", "verification": {"status": "accept_all"}}}
        f = lookup.Hunter("k", fetch).find("Ann", "Bee", "Acme", "acme.example", "")
        self.assertEqual(lookup.check(f, "acme.example"), (False, "unverified_accept_all"))
        self.assertIsNone(lookup.Hunter("k", fetch).find("Ann", "Bee", "Acme", "", ""))


if __name__ == "__main__":
    unittest.main()
