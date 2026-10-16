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
python3 -m crm daily --out today.md                                 # new people (prospecting.toml) + checks + ~20 drafts + LinkedIn notes
python3 -m crm sent                                                 # after sending them from your mailbox
python3 -m crm li invited <id> <id>                                 # after sending LinkedIn invitations (also: accepted, messaged, replied, declined, skip)
```

## Automatic prospecting

Each morning `crm daily` (or `crm prospect` on its own) finds new people itself, with no data company in the middle, and adds the ones with a checked work email. What it looks for lives in [`prospecting.toml`](prospecting.toml): area, company size, industries, job titles, which email checks are good enough, and daily limits.

1. **Companies House** (official, free API): active limited companies, PLCs and LLPs whose registered office is in your area, optionally filtered by industry (SIC code), sized by the type of accounts they last filed.
2. **The register's officers**: directors whose stated occupation matches a target title, such as "Finance Director" or "Chartered Accountant".
3. **The company's own website**: the CRM tries the likely domains and only accepts one that shows the company's registered number or postcode (UK companies must show these), then reads up to six pages (home, about, team, contact, legal) for names beside matching job titles and for any published work addresses. It honours robots.txt, waits 3 seconds between pages and identifies itself.
4. **The email**: `published` (on their website), `verified` (their mail server accepted it; nothing is sent), `pattern` (built from the format a named colleague's published address uses) or `guess`. Only the statuses in `accept` are used; guesses are off by default because bounces damage a new domain.
5. **The usual rules**: the suppression list (an unsubscribe is never undone by prospecting), corporate addresses only (PECR), de-duplication against everyone already in the CRM, and a privacy line in the first email saying the details came from Companies House and the company's website (UK GDPR Article 14).

It never touches LinkedIn. Companies, people and searches already checked are remembered, so each day moves on to new firms, and the daily caps hold across re-runs.

### Setting it up

1. Get a free Companies House API key: register at [developer.company-information.service.gov.uk](https://developer.company-information.service.gov.uk/), create an application, add a REST key, then `export COMPANIES_HOUSE_API_KEY=...`.
2. Set `location` in `prospecting.toml` (it won't run until you do) and adjust the titles and sizes.
3. Set `CRM_RECRUITER_EMAIL` to your real business address: the mail server check introduces itself with it.
4. Try it: `python3 -m crm prospect --dry-run` shows who it would add, saving nothing.
5. Run it every weekday morning, on whichever machine holds `crm.sqlite3`: `30 7 * * 1-5 cd /path/to/crm && python3 -m crm daily --out today.md`.

### What it costs, and how it compares with paying Apollo

| Route | Cost | Notes |
|---|---|---|
| Our own (default) | £0 | Companies House API, company websites and DNS are free. |
| Mail server check | £0 | Needs outgoing port 25, which most home broadband and many cloud hosts block. It switches itself off when blocked and you still get `published` and `pattern` emails. |
| Hunter as a fallback (`fallback = "hunter"`) | Free plan: 50 credits a month | Paid plans start around $34 to $49 a month (Hunter's pricing page, October 2026). Only spent on people we found but couldn't confirm. |
| Apollo instead (`source = "apollo"`) | Free plan has limited API access and credits | Paid plans from about $49 a user a month billed yearly (third-party write-ups, September 2026; check Apollo's own page). People search is free of credits; each email costs one. |

Honest limits of doing it ourselves: the register only names directors, so financial controllers and finance managers are found only when their company lists them on its website, and many small firms don't. Expect plenty of companies to yield nobody (that's why it checks 40 a day), fewer people per day than a paid database, and some `pattern` addresses to bounce. What we gain: no subscription, no shared list that every other agency is also emailing, and a clear, checkable source for every person. Apollo stays available as a switch in the config if volume matters more than cost.

| Module | Job |
|---|---|
| `crm/prospect.py` | The daily prospecting run: config, caps, de-duplication, compliance checks, Apollo route. |
| `crm/companies_house.py` | Companies House search, company size, officers. |
| `crm/website.py` | Finds and confirms a company's website, reads team and contact pages. |
| `crm/emailfind.py` | Email formats, MX lookup, polite mail server check. |
| `crm/net.py` | robots.txt, spacing between requests, user agent. |

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
5. An Anthropic API key, a free Companies House API key for prospecting (a paid data provider is optional), and somewhere to host it (a small VPS or a platform like Railway or Fly.io running `crm serve` and the cron jobs).
6. A private GitHub repository so the code can be worked on from any computer.
