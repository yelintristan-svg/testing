# Recruitment CRM and outreach engine (prototype)

One CRM shared by the three agencies (care and nursing, engineering and trades, accounting and finance). It stores candidates and client contacts, writes personalised emails with Claude, runs multi-step sequences at a safe pace, enforces UK GDPR and PECR, hands booked meetings to Tristan, and writes a morning standup for the AI assistants.

It follows the [business blueprint](../blueprint/business-blueprint.md). Brands: Wrenfield Finance (launching first), Wrenfield Care and Wrenfield Build (both parked), under Wrenfield Talent Group.

Status: working prototype. Everything runs locally with no API key and **no real email is ever sent**: messages are written as `.eml` files in `outbox/`.

## Lean launch: your daily list

For the Wrenfield Finance launch, Tristan sends about 20 emails a day himself from one business mailbox, and sends LinkedIn invitations by hand. The CRM finds the emails, checks them, drafts everything and keeps track. The full routine is in [finance-launch-plan.md](../blueprint/finance-launch-plan.md#5-the-daily-routine-about-an-hour).

```bash
python3 -m crm add-assistant tristan "Tristan" tristan@wrenfieldfinance.co.uk \
    https://calendly.com/<tristan>/intro --brand finance --human     # a person, not an AI: no AI line, sends by hand
python3 -m crm load-sequences sequences/finance_*.json
python3 -m crm targets today.txt --brand finance --kind client      # 'name | title | company | profile url | domain | why' lines, or an Apollo CSV
python3 -m crm daily --out today.md                                 # email lookup + checks + ~20 drafts + LinkedIn notes
python3 -m crm sent                                                 # after sending them from your mailbox
python3 -m crm li invited <id> <id>                                 # after sending LinkedIn invitations (also: accepted, messaged, replied, declined, skip)
```

| Module | Job |
|---|---|
| `crm/daily.py` | The daily list: people in from a pasted list or CSV, email lookup, top-up to `CRM_DAILY_EMAILS`, LinkedIn notes within LinkedIn's limits, the Markdown list with "open in mail app" links. |
| `crm/lookup.py` | Apollo People Match and Hunter Email Finder. Keeps only addresses the provider has verified, on the company's own domain, never personal ones. |

Senders added with `--human` are never sent through the mailer (`CRM_HAND_SEND=true`); their emails wait on the daily list until `crm sent` logs them. Set `CRM_UNSUB_MODE=reply` until the unsubscribe page is hosted, so the footer asks for a reply instead of linking to localhost.

## Quick start (AI assistants sending)

```bash
cd crm
python3 -m unittest discover -s tests          # end-to-end tests

export CRM_DB=crm.sqlite3                       # all settings: crm/settings.py
python3 -m crm init
python3 -m crm add-assistant ava "Ava, AI Recruitment Assistant" ava@outreach.example \
    https://calendly.com/<tristan>/intro
python3 -m crm add-assistant max "Max, AI Recruitment Assistant" max@outreach.example \
    https://calendly.com/<tristan>/intro --brand engineering
python3 -m crm load-sequences sequences/*.json
python3 -m crm import sample_data/apollo_sample.csv --kind client --brand engineering
python3 -m crm enroll engineering_clients_bd ava
python3 -m crm tick        # drafts the first emails
python3 -m crm review      # read them
python3 -m crm approve     # approve all (or pass message ids)
python3 -m crm tick        # sends within the caps, into outbox/
python3 -m crm standup
```

To use Claude for drafting instead of the offline template: `pip install -r requirements.txt`, set `ANTHROPIC_API_KEY`, and `CRM_LLM=claude`. The default model is `claude-opus-5-5` (`CRM_MODEL` to change it; at very high volume a cheaper model such as `claude-haiku-5-5` is worth testing on a sample first).

## How it works

| Module | Job |
|---|---|
| `crm/db.py` | SQLite schema: brands, assistants, organisations, contacts, notes, sequences, enrollments, messages, meetings, suppressions, audit log. Ports to Postgres with type tweaks. |
| `crm/importers.py` | CSV imports from Apollo (Lusha, Cognism and ZoomInfo exports map the same way) and records added by hand. De-duplicates, skips unverified addresses, records source and lawful basis. |
| `crm/personalise.py` | Claude drafts each email from the profile and Tristan's notes, returned as JSON. Profile text is treated as untrusted data. Every draft passes a validator (length, booking link, no placeholders, no fake "we spoke" claims). Also classifies replies. |
| `crm/engine.py` | Sequences, drafting, review queue, throttled sending, reply and bounce handling. |
| `crm/compliance.py` | PECR and GDPR rules (below), unsubscribe links, erasure, subject access export, retention purge. |
| `crm/booking.py` | Calendly webhook: verifies the signature, records the meeting, stops outreach, writes Tristan's briefing, queues the assistant's confirmation, writes an `.ics`. |
| `crm/standup.py` | Morning brief: today's calls, warm replies, drafts to approve, each assistant's numbers, compliance holds, pipeline. |
| `crm/web.py` | Unsubscribe page (with RFC 8058 one-click) and the Calendly webhook endpoint. |

### Sending pace

Per mailbox: warm-up ramp from 10 to 40 a day over 28 days, 12 an hour, at least 90 seconds apart, weekdays 08:00 to 18:00 UK time. All configurable. More volume means more mailboxes, not a higher cap per mailbox, and they should sit on a separate outreach domain so the main company domain's reputation is protected.

### Connecting a sending platform

The blueprint recommends Instantly or Smartlead for the actual sending (inbox rotation, warm-up, reply detection). `crm/mailer.py` is the seam for that: a mailer only needs a `send(message, message_id)` method, so an Instantly or Smartlead mailer can replace the dry-run one, with their reply and bounce webhooks calling `engine.record_reply` and `engine.record_bounce`. The built-in caps still apply on top as a safety net.

The schema uses plain SQL, so moving from SQLite to Supabase (Postgres) is a connection change plus column types.

### Compliance rules the code enforces

- **PECR:** corporate addresses can be emailed under legitimate interests with an opt-out in every message. Personal addresses (gmail and similar) and unverified domains are blocked unless consent is recorded, for example from a website sign-up.
- **Article 14:** the first email says where the details came from and links the brand's privacy notice.
- **Opt-out:** an unsubscribe, by link or by reply, stops all three brands at once and survives re-imports.
- **Erasure:** deletes the person and keeps only a hash so they can't be re-imported and emailed.
- **Retention:** contacts with no activity for 365 days are purged (`crm purge`).
- **AI disclosure:** every email from an assistant says it is an AI assistant working with Tristan, Head of Recruitment.
- **Human in the loop:** first-touch drafts wait for approval by default (`CRM_REQUIRE_REVIEW`). Any human reply stops automation.

This is engineering, not legal advice. Have the privacy notices and legitimate interest assessments checked before going live.

### Booking handoff

Each assistant's booking link points at a Calendly event type owned by **Tristan's** Calendly account, connected to his calendar. A booking from any assistant therefore lands on Tristan's calendar with him as host. The link carries `utm_content=<contact id>`, so the webhook matches the booking to the right person. The assistant then sends: "You're confirmed with Tristan, our Head of Recruitment... I passed your details to Tristan because your experience looked like a strong fit."

## Not built, on purpose

- **No LinkedIn scraping or LinkedIn automation.** LinkedIn's terms forbid both and ban the accounts involved. The CRM never visits LinkedIn: profile URLs are what Tristan noted himself, kept as a reference and as a matching key for Apollo. Invitations and messages are drafted here and sent by Tristan.
- **No sending from personal mailboxes.** `add-assistant` refuses gmail.com, outlook.com and similar addresses as senders.
- **No live sending.** `CRM_MAILER=smtp` exists but refuses to run without `CRM_ALLOW_LIVE_SEND=true`.

## Before going live (needs Tristan)

1. Company domains for the group and the three brands, plus a separate outreach domain with SPF, DKIM and DMARC.
2. Mailboxes for the assistants (Google Workspace or Microsoft 365), warmed up.
3. ICO registration, privacy notices per brand, and a review of the legitimate interest assessments stored on each brand.
4. Calendly: event types under Tristan's account, a webhook subscription pointing at `/webhooks/calendly`, and the signing key in `CALENDLY_WEBHOOK_SIGNING_KEY`.
5. An Anthropic API key, a data provider account (such as Apollo) for imports, and somewhere to host it (a small VPS or a platform like Railway or Fly.io running `crm serve` and the cron jobs).
6. A private GitHub repository so the code can be worked on from any computer.
