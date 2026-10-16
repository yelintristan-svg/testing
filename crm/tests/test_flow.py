"""End-to-end tests. Run: python -m unittest discover -s tests (from the crm folder)."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crm import booking, compliance, db, engine, importers, standup  # noqa: E402
from crm.mailer import DryRunMailer  # noqa: E402
from crm.personalise import Draft, DraftRejected, Writer, validate_draft  # noqa: E402
from crm.settings import Settings  # noqa: E402
from crm.web import make_app  # noqa: E402

# Tuesday 20 Oct 2026, 10:00 London (BST) = 09:00 UTC
T0 = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.s = Settings()
        self.s.db_path = self.tmp / "t.db"
        self.s.outbox_dir = self.tmp / "outbox"
        self.s.llm = "offline"
        self.s.calendly_signing_key = "test-signing-key"
        self.conn = db.connect(self.s.db_path)
        db.init(self.conn)
        engine.add_assistant(self.conn, "ava", "Ava, AI Recruitment Assistant", "ava@outreach.example",
                             "https://calendly.com/example-tristan/intro", started_on="2026-01-01")
        for f in (ROOT / "sequences").glob("*.json"):
            engine.load_sequence(self.conn, f)
        self.counts = importers.import_csv(self.conn, ROOT / "sample_data/apollo_sample.csv",
                                           kind="client", brand_id="engineering")
        self.mailer = DryRunMailer(self.s.outbox_dir)
        self.writer = Writer(self.s)

    def tearDown(self):
        self.conn.close()

    def contact(self, email):
        return self.conn.execute("SELECT * FROM contacts WHERE email=?", (email,)).fetchone()

    def enroll_all(self):
        out = {}
        for c in self.conn.execute("SELECT * FROM contacts").fetchall():
            _, r = engine.enroll(self.conn, c["id"], "engineering_clients_bd", "ava", start_at=T0)
            out[c["email"]] = r
        return out


class ImportAndCompliance(Base):
    def test_import_classifies_and_skips(self):
        self.assertEqual(self.counts, {"created": 3, "skipped_bad_email": 1})
        self.assertEqual(self.contact("priya.shah@northbank-build.example")["email_type"], "corporate")
        self.assertEqual(self.contact("dan.moss@gmail.com")["email_type"], "personal")

    def test_pecr_blocks_personal_address_without_consent(self):
        r = self.enroll_all()
        self.assertEqual(r["dan.moss@gmail.com"], "pecr_personal_address_needs_consent")
        self.assertEqual(r["priya.shah@northbank-build.example"], "enrolled")

    def test_consent_allows_personal_address(self):
        cid, _ = importers.add_contact(self.conn, kind="candidate", brand_id="care", email="nurse@gmail.com",
                                       source="website_form", lawful_basis="consent", consent_at=db.now(),
                                       first_name="Sam")
        ok, why = compliance.can_email(self.conn, self.conn.execute("SELECT * FROM contacts WHERE id=?", (cid,)).fetchone())
        self.assertTrue(ok, why)

    def test_unsubscribe_is_group_wide_and_survives_reimport(self):
        importers.add_contact(self.conn, kind="candidate", brand_id="finance", email="tom@hughesmech.example",
                              source="manual", company="Hughes Mechanical", domain="hughesmech.example")
        compliance.suppress(self.conn, "Tom@HughesMech.example", "unsubscribe")
        self.conn.commit()
        rows = self.conn.execute("SELECT status FROM contacts WHERE email='tom@hughesmech.example'").fetchall()
        self.assertEqual({r["status"] for r in rows}, {"do_not_contact"})
        _, outcome = importers.add_contact(self.conn, kind="candidate", brand_id="care",
                                           email="tom@hughesmech.example", source="manual")
        self.assertEqual(outcome, "skipped_suppressed")

    def test_erasure_deletes_but_keeps_block(self):
        n = compliance.erase(self.conn, "priya.shah@northbank-build.example", actor="test")
        self.assertEqual(n, 1)
        self.assertIsNone(self.contact("priya.shah@northbank-build.example"))
        row = self.conn.execute("SELECT * FROM suppressions").fetchone()
        self.assertIsNone(row["email"])
        self.assertTrue(compliance.is_suppressed(self.conn, "priya.shah@northbank-build.example"))

    def test_subject_access_export(self):
        out = compliance.subject_access_export(self.conn, "priya.shah@northbank-build.example")
        self.assertEqual(len(out["contacts"]), 1)
        self.assertEqual(out["contacts"][0]["record"]["source"], "apollo_csv")


class SequenceFlow(Base):
    def test_full_flow(self):
        self.enroll_all()
        r = engine.tick(self.conn, self.s, self.writer, self.mailer, now=T0)
        self.assertEqual(r["draft"], {"drafted_for_review": 2})
        self.assertNotIn("sent", r["send"])  # first touches wait for review

        # Ticking again must not double-draft.
        r = engine.tick(self.conn, self.s, self.writer, self.mailer, now=T0)
        self.assertEqual(r["draft"], {})

        engine.approve(self.conn)
        r1 = engine.send_due(self.conn, self.s, self.mailer, now=T0)
        r2 = engine.send_due(self.conn, self.s, self.mailer, now=T0 + timedelta(seconds=30))
        r3 = engine.send_due(self.conn, self.s, self.mailer, now=T0 + timedelta(minutes=2))
        self.assertEqual(r1.get("sent"), 1)
        self.assertIn("held_min_gap", r2)
        self.assertEqual(r3.get("sent"), 1)

        emls = list(self.s.outbox_dir.glob("*.eml"))
        self.assertEqual(len(emls), 2)
        import email
        from email import policy as _pol
        parsed = email.message_from_bytes(emls[0].read_bytes(), policy=_pol.default)
        self.assertEqual(parsed["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertRegex(parsed["List-Unsubscribe"], r"^<http://localhost:8080/u\?e=")
        text = parsed.get_content()
        self.assertIn("I'm an AI assistant", text)
        self.assertIn("We found your professional details via", text)
        self.assertIn("utm_content=con_", text)
        self.assertNotIn("{BOOKING_LINK}", text)

        # Step 2 is due 4 days later (Saturday), so it waits for Monday and goes out without review.
        sat = T0 + timedelta(days=4, minutes=5)
        r = engine.tick(self.conn, self.s, self.writer, self.mailer, now=sat)
        self.assertEqual(r["draft"], {"drafted_auto_approved": 2})
        self.assertIn("held_weekend", r["send"])
        later = T0 + timedelta(days=6)
        r = engine.tick(self.conn, self.s, self.writer, self.mailer, now=later)
        self.assertEqual(r["send"].get("sent"), 1)
        follow = self.conn.execute("SELECT body FROM messages WHERE step=1 AND status='sent'").fetchone()["body"]
        self.assertNotIn("We found your professional details", follow)  # Art. 14 notice only on first contact

        # Tom replies; his sequence stops and his queued follow-up is withdrawn.
        res = engine.record_reply(self.conn, self.s, "tom@hughesmech.example", "Re: hiring",
                                  "Sounds good, happy to chat next week", self.writer)
        self.assertEqual(res["intent"], "interested")
        tom = self.contact("tom@hughesmech.example")
        enr = self.conn.execute("SELECT status, stop_reason FROM enrollments WHERE contact_id=?", (tom["id"],)).fetchone()
        self.assertEqual(tuple(enr), ("stopped", "replied_interested"))
        open_msgs = self.conn.execute("SELECT COUNT(*) FROM messages WHERE contact_id=? AND status IN ('draft','approved')",
                                      (tom["id"],)).fetchone()[0]
        self.assertEqual(open_msgs, 0)

    def test_unsubscribe_reply_suppresses(self):
        self.enroll_all()
        engine.record_reply(self.conn, self.s, "priya.shah@northbank-build.example", "Re", "Please remove me from your list", self.writer)
        self.assertTrue(compliance.is_suppressed(self.conn, "priya.shah@northbank-build.example"))

    def test_out_of_office_keeps_sequence(self):
        self.enroll_all()
        engine.record_reply(self.conn, self.s, "priya.shah@northbank-build.example", "Auto", "I am out of the office until Monday", self.writer)
        c = self.contact("priya.shah@northbank-build.example")
        st = self.conn.execute("SELECT status FROM enrollments WHERE contact_id=?", (c["id"],)).fetchone()[0]
        self.assertEqual(st, "active")


class Throttling(Base):
    def test_send_window_weekend_and_warmup(self):
        a = self.conn.execute("SELECT * FROM assistants").fetchone()
        self.assertEqual(engine.capacity(self.conn, self.s, a, T0.replace(hour=20))[1], "outside_send_window")
        self.assertEqual(engine.capacity(self.conn, self.s, a, T0 + timedelta(days=4))[1], "weekend")
        self.assertEqual(engine.mailbox_cap(self.s, "2026-10-20", T0.date()), self.s.warmup_start_cap)
        self.assertEqual(engine.mailbox_cap(self.s, "2026-01-01", T0.date()), self.s.daily_cap)
        mid = engine.mailbox_cap(self.s, "2026-10-06", T0.date())
        self.assertTrue(self.s.warmup_start_cap < mid < self.s.daily_cap)

    def test_daily_cap(self):
        self.s.daily_cap = 1
        self.s.require_review = False
        self.enroll_all()
        engine.tick(self.conn, self.s, self.writer, self.mailer, now=T0)
        r = engine.send_due(self.conn, self.s, self.mailer, now=T0 + timedelta(minutes=10))
        self.assertIn("held_daily_cap_1", r)


class Booking(Base):
    def test_signed_webhook_books_and_hands_off(self):
        self.enroll_all()
        c = self.contact("priya.shah@northbank-build.example")
        ev = booking.sample_event(c, "ava", "2026-10-21T10:00:00Z", "2026-10-21T10:15:00Z")
        raw = booking.dumps(ev)
        app = make_app(self.s)

        def call(sig):
            env = {"PATH_INFO": "/webhooks/calendly", "REQUEST_METHOD": "POST", "QUERY_STRING": "",
                   "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw),
                   "HTTP_CALENDLY_WEBHOOK_SIGNATURE": sig}
            status = {}
            body = b"".join(app(env, lambda s, h: status.setdefault("s", s)))
            return status["s"], body

        self.assertTrue(call("t=1,v1=bad")[0].startswith("401"))
        status, body = call(booking.sign(self.s.calendly_signing_key, raw))
        self.assertTrue(status.startswith("200"), body)
        self.assertEqual(json.loads(body)["status"], "booked")

        m = self.conn.execute("SELECT * FROM meetings").fetchone()
        self.assertEqual(m["host_name"], "Tristan")
        self.assertIn("Site Manager", m["briefing"])
        self.assertEqual(self.contact("priya.shah@northbank-build.example")["status"], "meeting")
        handoff = self.conn.execute("SELECT * FROM messages WHERE subject LIKE 'Confirmed:%'").fetchone()
        self.assertEqual(handoff["status"], "approved")
        self.assertIn("Head of Recruitment", handoff["body"])
        self.assertTrue(list(self.s.outbox_dir.glob("*.ics")))
        # Calendly retries deliveries; a duplicate must not double-book.
        self.assertEqual(booking.handle_webhook(self.conn, self.s, ev)["status"], "duplicate")

    def test_unsubscribe_link(self):
        app = make_app(self.s)
        email = "priya.shah@northbank-build.example"
        tok = compliance.unsubscribe_token(self.s.unsubscribe_secret, email)
        env = {"PATH_INFO": "/u", "REQUEST_METHOD": "POST", "QUERY_STRING": f"e={email}&t={tok}",
               "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO(b"")}
        b"".join(app(env, lambda s, h: None))
        self.conn.commit()
        self.assertTrue(compliance.is_suppressed(self.conn, email))


class Standup(Base):
    def test_standup_sections(self):
        self.enroll_all()
        engine.tick(self.conn, self.s, self.writer, self.mailer, now=T0)
        md = standup.build(self.conn, self.s, now=T0 + timedelta(days=1))
        for section in ("Your calls today", "Replies that need you", "Waiting for your approval",
                        "Yesterday, by assistant", "Compliance and deliverability", "Pipeline"):
            self.assertIn(section, md)
        self.assertIn("personal or unverified addresses", md)


class Drafting(Base):
    def test_validator(self):
        ok = Draft("Hiring", "Hi Priya, " + "word " * 40 + "{BOOKING_LINK}", [])
        validate_draft(ok)
        with self.assertRaises(DraftRejected):
            validate_draft(Draft("Hi", "Hi [First Name], " + "word " * 40 + "{BOOKING_LINK}", []))
        with self.assertRaises(DraftRejected):
            validate_draft(Draft("Hi", "Hi Priya, " + "word " * 40, []))
        with self.assertRaises(DraftRejected):
            validate_draft(Draft("Hi", "Great speaking yesterday, " + "word " * 40 + "{BOOKING_LINK}", []))

    def test_claude_request_shape(self):
        captured = {}
        body = "Hi Priya,\n\n" + "Your groundworks experience stands out. " * 6 + "Book here: {BOOKING_LINK}"

        class FakeMessages:
            def create(self, **kw):
                captured.update(kw)
                return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(
                    type="text", text=json.dumps({"subject": "Groundworks hiring", "body": body,
                                                  "personal_hooks": ["groundworks"]}))])

        self.s.llm = "claude"
        w = Writer(self.s)
        w._client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))
        c = self.contact("priya.shah@northbank-build.example")
        a = self.conn.execute("SELECT * FROM assistants").fetchone()
        step = {"kind": "first_touch", "index": 0, "sequence_name": "x", "goal": "y", "brief": "z"}
        d = w.draft(self.conn, c, a, step, [])
        self.assertEqual(d.subject, "Groundworks hiring")
        self.assertEqual(captured["model"], "claude-opus-5-5")
        self.assertEqual(captured["output_config"]["format"]["type"], "json_schema")
        self.assertIn("<profile>", captured["messages"][0]["content"])
        self.assertIn("never claims to be human", captured["system"])

    def test_refusal_is_rejected(self):
        class FakeMessages:
            def create(self, **kw):
                return SimpleNamespace(stop_reason="refusal", content=[])
        self.s.llm = "claude"
        w = Writer(self.s)
        w._client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))
        with self.assertRaises(DraftRejected):
            w.classify_reply("hello")


if __name__ == "__main__":
    unittest.main()
