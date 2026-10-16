"""Automatic prospecting, end to end, with every network call mocked.

No real API keys, no real websites, no mail servers, nothing sent.
"""
from __future__ import annotations

import base64
import json
import shutil
import sys
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crm import companies_house, compliance, daily, db, emailfind, engine, lookup, net, prospect, website  # noqa: E402
from crm.personalise import Writer  # noqa: E402
from crm.settings import Settings  # noqa: E402

T0 = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)  # Tuesday morning

COMPANIES = [
    {"company_number": "01234567", "company_name": "BROOK FOODS LIMITED", "sic_codes": ["10890"],
     "registered_office_address": {"locality": "Manchester", "postal_code": "M1 2AB"}},
    {"company_number": "07654321", "company_name": "TINY TRADING LTD", "sic_codes": ["46900"],
     "registered_office_address": {"locality": "Manchester", "postal_code": "M4 1AA"}},
    {"company_number": "05555555", "company_name": "COLE & CO ENGINEERING LIMITED", "sic_codes": ["25110"],
     "registered_office_address": {"locality": "Salford", "postal_code": "M5 3AA"}},
    {"company_number": "06666666", "company_name": "FORD GROUP LIMITED", "sic_codes": ["46900"],
     "registered_office_address": {"locality": "Manchester", "postal_code": "M2 9ZZ"}},
    {"company_number": "08888888", "company_name": "ACME PARTS LTD", "sic_codes": ["28990"],
     "registered_office_address": {"locality": "Stockport", "postal_code": "SK1 1AA"}},
    {"company_number": "09999999", "company_name": "SLEEPY HOLDINGS LIMITED", "sic_codes": ["99999"],
     "registered_office_address": {"locality": "Manchester", "postal_code": "M3 3AA"}},
]
ACCOUNTS = {"01234567": "small", "07654321": "micro-entity", "05555555": "medium", "06666666": "total-exemption-full",
            "08888888": "unaudited-abridged", "09999999": "dormant"}
OFFICERS = {
    "01234567": [{"name": "SMITH, Jane Mary", "officer_role": "director", "occupation": "Finance Director"},
                 {"name": "JONES, David", "officer_role": "director", "occupation": "Managing Director"},
                 {"name": "OLD, Former", "officer_role": "director", "occupation": "Finance Director",
                  "resigned_on": "2024-01-01"},
                 {"name": "BROOK SECRETARIES LIMITED", "officer_role": "corporate-secretary"}],
    "05555555": [{"name": "LEE, Dr Amy", "officer_role": "director", "occupation": "Chartered Accountant"}],
    "06666666": [{"name": "FORD, Ben", "officer_role": "director", "occupation": "Company Director"}],
    "08888888": [{"name": "BROWN, Tom", "officer_role": "director", "occupation": "Finance Director"}],
}


class FakeCH:
    def __init__(self, companies=COMPANIES):
        self.companies, self.calls = companies, []

    def search(self, *, start_index=0, size=50, **kw):
        self.calls.append(("search", start_index, kw.get("location")))
        return self.companies[start_index:start_index + size], len(self.companies)

    def profile(self, number):
        return {"accounts": {"last_accounts": {"type": ACCOUNTS[number]}}}

    def officers(self, number):
        items = OFFICERS.get(number, [])
        status, _, text = 200, "", json.dumps({"items": items})
        real = companies_house.CompaniesHouse("k", get=lambda url, h: (status, url, text), sleep=lambda s: None)
        return real.officers(number)


BROOK_HOME = """<html><body><nav><a href="/our-team">Meet the team</a> <a href="/contact">Contact us</a>
<a href="/brochure.pdf">Brochure</a></nav><h1>Brook Foods</h1><p>Family bakers since 1982.</p>
<footer>Brook Foods Limited. Registered in England No. 1234567. M1 2AB</footer></body></html>"""
BROOK_TEAM = """<html><body><h2>Our people</h2>
<div><h3>Raj Patel ACA</h3><p>Financial Controller</p><p>raj.patel [at] brookfoods [dot] co [dot] uk</p></div>
<div><h3>Sarah Lee</h3><p>Head of Marketing</p></div>
<div><h3>Jane Smith</h3><p>Finance Director</p></div>
<script>var x = "Finance Director Fake Person";</script></body></html>"""
BROOK_CONTACT = """<p>Call us or email <a href="mailto:info@brookfoods.co.uk">info@brookfoods.co.uk</a>.
For supplier accounts: <a href="mailto:david.jones@brookfoods.co.uk">David Jones</a></p>"""
ACME_HOME = """<p>Acme Parts Ltd, company number 08888888.</p><p>Tom Brown | Finance Director</p>
<p>tom.brown@acmeparts.co.uk</p>"""
FORD_HOME = "<p>Ford Group: a completely different business in Kent. Company no. 11112222.</p>"


def mx_json(host):
    return json.dumps({"Answer": [{"type": 15, "data": f"10 {host}."}]})


class FakeWeb:
    def __init__(self, extra=None):
        self.pages = {
            "https://brookfoods.co.uk/": BROOK_HOME,
            "https://brookfoods.co.uk/our-team": BROOK_TEAM,
            "https://brookfoods.co.uk/contact": BROOK_CONTACT,
            "https://acmeparts.co.uk/": ACME_HOME,
            "https://fordgroup.co.uk/": FORD_HOME,
            "https://fordgroup.com/robots.txt": "User-agent: *\nDisallow: /",
            "https://fordgroup.com/": "<p>Ford Group Limited 06666666 Finance Director: Ben Ford</p>",
        }
        self.pages.update(extra or {})
        self.seen: list[str] = []

    def __call__(self, url, headers):
        self.seen.append(url)
        if url.startswith("https://cloudflare-dns.com/"):
            name = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["name"][0]
            return 200, url, mx_json(f"mx.{name}")
        if url in self.pages:
            return 200, url, self.pages[url]
        if url.endswith("/robots.txt"):
            return 404, url, ""
        return 0, url, ""


class FakeSMTP:
    """Pretends to be a mail server. RCPT answers 250 only for `accept` (or everything if catch_all)."""
    log: list = []

    def __init__(self, accept=(), catch_all=False, fail=False):
        self.accept, self.catch_all, self.fail = set(accept), catch_all, fail

    def __call__(self, host, port, timeout=None):
        if self.fail:
            raise OSError("port 25 blocked")
        outer = self

        class Conn:
            def ehlo(self, name):
                FakeSMTP.log.append(("ehlo", name))
                return 250, b"ok"

            def mail(self, addr):
                return 250, b"ok"

            def rcpt(self, addr):
                FakeSMTP.log.append(("rcpt", addr))
                return (250, b"ok") if outer.catch_all or addr in outer.accept else (550, b"no such user")

            def data(self, *a):
                raise AssertionError("prospecting must never send a message")

            def quit(self):
                FakeSMTP.log.append(("quit", host))
        return Conn()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.s = Settings()
        self.s.db_path, self.s.outbox_dir, self.s.llm = self.tmp / "t.db", self.tmp / "outbox", "offline"
        self.s.unsub_mode = "reply"
        self.s.recruiter_email = "tristan@wrenfieldfinance.example"
        self.s.prospect_config = self.tmp / "no-prospecting.toml"
        self.conn = db.connect(self.s.db_path)
        db.init(self.conn)
        self.cfg = prospect.Config(location="Manchester", exclude_sic_codes=["99999"],
                                   candidate_titles=["chartered accountant", "accountant"])
        self.web = FakeWeb()
        FakeSMTP.log = []
        compliance.suppress(self.conn, "tom.brown@acmeparts.co.uk", "unsubscribe")   # he opted out last month
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def go(self, cfg=None, smtp=None, **kw):
        cfg = cfg or self.cfg
        polite = net.Polite("TestBot/1.0", gap=0, get=self.web, sleep=lambda s: None)
        prober = emailfind.SmtpProber("wrenfieldfinance.example", self.s.recruiter_email,
                                      connect=smtp or FakeSMTP(accept={"jane.smith@brookfoods.co.uk"}))
        kw.setdefault("ch", FakeCH())
        kw.setdefault("now", T0)
        return prospect.run(self.conn, self.s, cfg, polite=polite, dns_get=self.web, prober=prober, **kw)

    def contacts(self):
        return {r["email"]: r for r in self.conn.execute(
            "SELECT c.*, o.name AS org, o.size AS org_size FROM contacts c"
            " LEFT JOIN organisations o ON o.id=c.organisation_id")}


class Pipeline(Base):
    def test_finds_people_and_checked_work_emails(self):
        res = self.go()
        c = self.contacts()
        self.assertEqual(set(c), {"jane.smith@brookfoods.co.uk", "raj.patel@brookfoods.co.uk"})
        jane, raj = c["jane.smith@brookfoods.co.uk"], c["raj.patel@brookfoods.co.uk"]
        self.assertEqual((jane["first_name"], jane["last_name"], jane["title"]), ("Jane", "Smith", "Finance Director"))
        self.assertEqual((raj["kind"], raj["title"], raj["org_size"]), ("client", "Financial Controller", "small"))
        self.assertEqual(jane["email_type"], "corporate")
        self.assertIn("Companies House", jane["source_detail"])     # Article 14 line in the first email
        ok, why = compliance.can_email(self.conn, jane)
        self.assertTrue(ok, why)
        statuses = {a["email"]: a["status"] for a in res["added"]}
        self.assertEqual(statuses, {"jane.smith@brookfoods.co.uk": "verified",
                                    "raj.patel@brookfoods.co.uk": "published"})
        counts = res["counts"]
        self.assertEqual(counts["companies_checked"], 6)
        self.assertEqual(counts["wrong_size"], 1)           # the micro company
        self.assertEqual(counts["excluded_industry"], 1)    # the dormant one
        self.assertEqual(counts["no_people"], 1)            # Ford: no finance staff found
        self.assertEqual(counts["no_website"], 1)           # Cole & Co: Amy found, nowhere to email her
        self.assertEqual(counts["skipped_suppressed"], 1)   # Tom unsubscribed earlier: stays unsubscribed

    def test_never_sends_and_checks_politely(self):
        self.go()
        rcpts = [a for k, a in FakeSMTP.log if k == "rcpt"]
        self.assertTrue(rcpts[0].startswith("zz-"))         # made-up address first: spots catch-all servers
        self.assertIn("jane.smith@brookfoods.co.uk", rcpts)
        self.assertLessEqual(len(rcpts), 4)
        self.assertIn(("quit", "mx.brookfoods.co.uk"), FakeSMTP.log)

    def test_respects_robots_and_rejects_namesake_sites(self):
        self.go()
        self.assertIn("https://fordgroup.com/robots.txt", self.web.seen)
        self.assertNotIn("https://fordgroup.com/", self.web.seen)     # robots.txt said keep out
        row = self.conn.execute("SELECT * FROM prospect_companies WHERE company_number='06666666'").fetchone()
        self.assertIsNone(row["domain"])                               # fordgroup.co.uk is someone else's
        self.assertNotIn("https://brookfoods.co.uk/brochure.pdf", self.web.seen)

    def test_rerun_moves_on_and_never_duplicates(self):
        self.go()
        first = len(self.contacts())
        res = self.go()
        self.assertEqual(len(self.contacts()), first)
        self.assertEqual(res["added"], [])
        self.assertEqual(res["counts"].get("companies_checked", 0), 0)

    def test_already_in_crm_is_skipped(self):
        from crm import importers
        importers.add_contact(self.conn, kind="client", brand_id="finance", email="jane.s@brookfoods.co.uk",
                              source="manual", company="Brook Foods", domain="brookfoods.co.uk",
                              first_name="Jane", last_name="Smith")
        self.conn.commit()
        res = self.go()
        self.assertEqual(res["counts"]["already_in_crm"], 1)
        self.assertNotIn("jane.smith@brookfoods.co.uk", self.contacts())

    def test_daily_cap_counts_across_runs(self):
        self.cfg.new_contacts_per_day = 1
        self.assertEqual(len(self.go()["added"]), 1)
        self.assertEqual(len(self.go()["added"]), 0)                   # same day: cap already used
        later = prospect.run(self.conn, self.s, self.cfg, ch=FakeCH(),
                             polite=net.Polite("T", gap=0, get=self.web, sleep=lambda s: None), dns_get=self.web,
                             prober=emailfind.SmtpProber("x", "t@x", connect=FakeSMTP(
                                 accept={"jane.smith@brookfoods.co.uk"})),
                             now=datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(len(later["added"]), 1)                       # next day: the rest of Brook Foods

    def test_company_cap_and_cursor(self):
        self.cfg.companies_per_day = 2
        ch = FakeCH()
        self.go(ch=ch)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM prospect_companies").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT next_index FROM prospect_cursor").fetchone()[0], 2)
        self.go(ch=ch, now=datetime(2026, 10, 21, 8, tzinfo=timezone.utc))
        self.assertEqual(ch.calls[-1][1], 2)                            # next day starts where it stopped
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM prospect_companies").fetchone()[0], 4)

    def test_dry_run_saves_nothing(self):
        res = self.go(dry_run=True)
        self.assertEqual(len(res["added"]), 2)
        self.assertEqual(self.contacts(), {})
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM prospect_companies").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM prospect_usage").fetchone()[0], 0)

    def test_port_25_blocked_falls_back_to_company_format(self):
        res = self.go(smtp=FakeSMTP(fail=True))
        statuses = {a["email"]: a["status"] for a in res["added"]}
        self.assertEqual(statuses["jane.smith@brookfoods.co.uk"], "pattern")
        self.assertEqual(res["counts"]["smtp_check_unavailable"], 1)

    def test_catch_all_server_proves_nothing(self):
        res = self.go(smtp=FakeSMTP(catch_all=True))
        statuses = {a["email"]: a["status"] for a in res["added"]}
        self.assertEqual(statuses["jane.smith@brookfoods.co.uk"], "pattern")

    def test_guesses_are_not_used_unless_allowed(self):
        self.cfg.accept = ["published", "verified"]
        res = self.go(smtp=FakeSMTP(catch_all=True))
        self.assertEqual([a["email"] for a in res["added"]], ["raj.patel@brookfoods.co.uk"])
        row = self.conn.execute("SELECT * FROM prospect_people WHERE first_name='Jane'").fetchone()
        self.assertEqual((row["outcome"], row["email_status"]), ("unverified_pattern", "pattern"))

    def test_paid_fallback_inside_credit_cap(self):
        self.cfg.accept = ["published"]
        self.cfg.credits_per_day = 1

        class Hunter:
            calls = []

            def find(self, first, last, company, domain, url):
                Hunter.calls.append(first)
                return lookup.Found(f"{first.lower()}@{domain}", True, "valid", "hunter",
                                    lookup.Hunter.source_detail, domain)
        res = self.go(smtp=FakeSMTP(fail=True), fallback=Hunter())
        self.assertEqual(Hunter.calls, ["Jane"])                        # one credit, one lookup
        self.assertIn("jane@brookfoods.co.uk", self.contacts())
        self.assertEqual(res["counts"]["fallback_lookups"], 1)

    def test_fallback_personal_address_is_refused(self):
        self.cfg.accept = ["published"]

        class Bad:
            def find(self, *a):
                return lookup.Found("jane@gmail.com", True, "valid", "hunter", "x", "brookfoods.co.uk")
        res = self.go(smtp=FakeSMTP(fail=True), fallback=Bad())
        self.assertEqual(res["counts"]["personal_address"], 1)
        self.assertNotIn("jane@gmail.com", self.contacts())

    def test_erasure_forgets_the_prospect(self):
        self.go()
        compliance.erase(self.conn, "jane.smith@brookfoods.co.uk", actor="tristan")
        self.assertIsNone(self.conn.execute("SELECT 1 FROM prospect_people WHERE email=?",
                                            ("jane.smith@brookfoods.co.uk",)).fetchone())
        self.assertTrue(compliance.is_suppressed(self.conn, "jane.smith@brookfoods.co.uk"))

    def test_feeds_the_daily_list(self):
        engine.add_assistant(self.conn, "tristan", "Tristan", "tristan@wrenfieldfinance.example",
                             "https://calendly.com/example-tristan/intro", brand_id="finance", is_ai=False)
        for f in (ROOT / "sequences").glob("finance_*.json"):
            engine.load_sequence(self.conn, f)
        res = daily.build(self.conn, self.s, "tristan", "finance", writer=Writer(self.s), now=T0,
                          prospector=lambda conn, s: self.go())
        self.assertEqual(len(res["prospecting"]["added"]), 2)
        self.assertEqual(res["new_people"], 2)
        md = daily.render(self.conn, self.s, "tristan")      # prospect rows carry the real clock
        self.assertIn("New people found today (2)", md)
        self.assertIn("To: jane.smith@brookfoods.co.uk", md)


class Apollo(Base):
    def test_apollo_source_spends_one_credit_per_email(self):
        cfg = prospect.Config(source="apollo", location="Manchester", credits_per_day=2)

        class FakeApollo:
            def __init__(self):
                self.reveals = []

            def search(self, titles, locations, ranges, page):
                assert locations == ["Manchester, United Kingdom"]
                return [{"id": f"p{i}", "first_name": n} for i, n in enumerate(["Ann", "Bob", "Cat"])] if page == 1 else []

            def reveal(self, pid):
                self.reveals.append(pid)
                names = {"p0": ("Ann", "Ash", "ann.ash@ashco.example", "verified"),
                         "p1": ("Bob", "Bell", "bob@bellco.example", "guessed")}
                f, l, e, st = names[pid]
                return {"first_name": f, "last_name": l, "email": e, "email_status": st, "title": "Finance Director",
                        "organization": {"id": pid, "name": f"{l} Co", "primary_domain": e.rpartition("@")[2]}}
        a = FakeApollo()
        res = prospect.run(self.conn, self.s, cfg, apollo=a, now=T0)
        self.assertEqual(a.reveals, ["p0", "p1"])                       # credit cap of 2
        self.assertEqual(set(self.contacts()), {"ann.ash@ashco.example"})  # Bob's address is unverified
        self.assertEqual(res["counts"]["unverified_guessed"], 1)


class Parts(unittest.TestCase):
    def test_candidate_domains(self):
        d = website.candidate_domains("COLE & CO ENGINEERING LIMITED")
        self.assertIn("coleengineering.co.uk", d)
        self.assertEqual(website.candidate_domains("BROOK FOODS LIMITED")[:2], ["brookfoods.co.uk", "brookfoods.com"])

    def test_people_on_page(self):
        page = website.parse("https://x.example/team", BROOK_TEAM)
        people = website.people_on(page, ["finance director", "financial controller"])
        self.assertEqual([(p["first_name"], p["last_name"], p["title"]) for p in people],
                         [("Raj", "Patel", "Financial Controller"), ("Jane", "Smith", "Finance Director")])
        self.assertIn("raj.patel@brookfoods.co.uk", page.emails)        # [at] / [dot] written out
        inline = website.parse("u", "<li>Mrs Priya Shah FCCA – Head of Finance</li><li>Head of Finance</li>")
        self.assertEqual([(p["first_name"], p["last_name"]) for p in website.people_on(inline, ["head of finance"])],
                         [("Priya", "Shah")])

    def test_officer_names(self):
        self.assertEqual(companies_house.split_officer_name("SMITH, Dr Jane Mary"), ("Jane", "Smith"))
        self.assertEqual(companies_house.size_of({"accounts": {"last_accounts": {"type": "medium"}}}), "medium")
        self.assertEqual(companies_house.size_of({}), "unknown")

    def test_companies_house_request(self):
        seen = {}

        def get(url, headers):
            seen["url"], seen["auth"] = url, headers["Authorization"]
            return 200, url, json.dumps({"items": [{"company_number": "1"}], "hits": 1})
        ch = companies_house.CompaniesHouse("secret-key", get=get, sleep=lambda s: None)
        items, hits = ch.search(location="Leeds", sic_codes=["10890"], min_age_years=2,
                                today=datetime(2026, 10, 16).date())
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(seen["url"]).query)
        self.assertEqual((q["location"], q["company_status"], q["incorporated_to"]),
                         (["Leeds"], ["active"], ["2024-10-16"]))
        self.assertEqual(seen["auth"], "Basic " + base64.b64encode(b"secret-key:").decode())
        self.assertEqual(hits, 1)
        bad = companies_house.CompaniesHouse("k", get=lambda u, h: (401, u, ""), sleep=lambda s: None)
        with self.assertRaises(RuntimeError):
            bad.search(location="Leeds")

    def test_pattern_inference(self):
        emails = {"david.jones@x.example", "info@x.example"}
        self.assertEqual(emailfind.infer_pattern(emails, [("David", "Jones")]), "{first}.{last}")
        self.assertEqual(emailfind.infer_pattern({"djones@x.example"}, [("David", "Jones")]), "{f}{last}")
        self.assertIsNone(emailfind.infer_pattern({"info@x.example"}, [("David", "Jones")]))

    def test_mx_lookup(self):
        get = lambda u, h: (200, u, json.dumps({"Answer": [{"type": 15, "data": "20 b.example."},  # noqa: E731
                                                           {"type": 15, "data": "10 a.example."}]}))
        self.assertEqual(emailfind.mx_hosts("x.example", get), ["a.example", "b.example"])
        null = lambda u, h: (200, u, json.dumps({"Answer": [{"type": 15, "data": "0 ."}]}))  # noqa: E731
        self.assertEqual(emailfind.mx_hosts("x.example", null), [])

    def test_config_file(self):
        shipped = ROOT / "prospecting.toml"
        with self.assertRaisesRegex(ValueError, "set location"):
            prospect.load_config(shipped)
        tmp = Path(tempfile.mkdtemp()) / "p.toml"
        tmp.write_text(shipped.read_text().replace('location = ""', 'location = "Leeds"'))
        cfg = prospect.load_config(tmp)
        self.assertEqual((cfg.location, cfg.sizes, cfg.brand), ("Leeds", ["small", "medium"], "finance"))
        self.assertIn("financial controller", cfg.client_titles)
        tmp.write_text('location = "Leeds"\n[people]\ntitels = ["fd"]\n')
        with self.assertRaisesRegex(ValueError, "titels"):
            prospect.load_config(tmp)

    def test_daily_without_config_still_works(self):
        s = Settings()
        s.prospect_config = Path("/nonexistent/prospecting.toml")
        self.assertIn("skipped", prospect.run_from_settings(None, s))


if __name__ == "__main__":
    unittest.main()
