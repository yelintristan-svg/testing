# AI-Assisted Recruitment Agency: Business Blueprint

*Version 1 · 16 Oct 2026 · Owner: Tristan*

> **Assumption:** UK market (England first), UK law and UK salary/fee norms. If you plan to trade in the US, Ireland or elsewhere, sections 2, 6 and 8 change and should be revisited.

---

## 1. The model in one paragraph

One holding brand, three specialist sector brands, one human recruiter (Tristan, Head of Recruitment) and two **openly disclosed AI recruitment assistants**. The assistants research companies and candidates from compliant sources, enrich a shared CRM, write personalised email sequences, handle replies, and book qualified calls into Tristan's calendar. Tristan does what only a human can and should do: consultative calls, LinkedIn conversations, interviews, offers and relationship management. Websites, blogs and social channels run on an automated content pipeline (AI drafts, Tristan approves, a scheduler publishes) to drive organic and inbound traffic, so outreach is warm rather than cold over time.

**Why disclosed AI rather than "fake employees":** LinkedIn's User Agreement only allows real people to hold personal profiles, and fake profiles get the company page and Tristan's account restricted. Under UK consumer and data protection law, misrepresenting who is contacting someone is also a liability. A clearly branded AI assistant ("Ava, AI Recruitment Assistant at Wrenfield Care") still looks like a larger, well-run team, and it's a positive differentiator ("we respond within 5 minutes, 24/7") instead of a risk.

---

## 2. Brand architecture

**Chosen names (16 Oct 2026): Wrenfield.** One shared surname-style brand reads as an established British firm, is rare in recruitment ("Meridian" was dropped because an existing UK recruiter already trades under it), and lets the parked sectors launch later without a rebrand. Check Companies House, the UKIPO trade mark register and domain availability before buying anything; if Wrenfield is taken, the fallback is **Ashcombe**, used the same way.

> **Launch decision:** only Wrenfield Finance goes live first. Care and Build stay parked until Finance is placing regularly. See [finance-launch-plan.md](finance-launch-plan.md).

| Layer | Name | Audience | Role of the site |
|---|---|---|---|
| Group | **Wrenfield Talent Group** | Investors, large clients, partners, press | Credibility: who we are, three divisions, leadership, compliance and memberships, "book a call" |
| Sector 1 | **Wrenfield Care** (nursing, medical and care) | Care homes, private hospitals, clinics, home-care providers; nurses, HCAs, registered managers | Client/candidate toggle, jobs, blog, book a call / upload CV |
| Sector 2 | **Wrenfield Build** (engineering, construction and technical trades) | Contractors, M&E firms, manufacturers, housebuilders; engineers, site managers, QS, skilled trades | Same template |
| Sector 3 | **Wrenfield Finance** (accounting and finance) | SMEs, PE-backed businesses, practices; qualified and part-qualified accountants, finance leaders | Same template |

**Design principle:** one codebase, one design system, three colourways. A shared brand ("a Wrenfield company") makes the group look bigger, and each sector site still reads as a specialist.

**Team presentation on every site:**
- Tristan, Head of Recruitment (real photo, real bio, LinkedIn link).
- Two AI assistants with illustrated (not photographic) avatars, named, and labelled "AI Recruitment Assistant". Example: *Ava (Care & Finance)* and *Max (Engineering)*.

---

## 3. Perm vs temp by sector

You are one recruiter. Temp desks need someone on call to fill shifts at short notice, they need payroll funding (you pay workers weekly and get paid by clients on 30–60 day terms), and they carry heavier compliance. That shapes every recommendation below.

### 3.1 Nursing, medical and care: **Perm first, temp in phase 3**
- **Start perm:** registered nurses (RGN/RMN) into private hospitals and nursing homes, registered managers, deputy managers, clinical leads, and home-care managers. UK fees are typically 15–20% of salary, and there is a chronic shortage, so clients engage quickly.
- **Why not temp yet:** agency nursing and care shifts are a 24/7 operation. They need enhanced DBS, right-to-work, NMC PIN and training compliance files for every worker, plus a funded weekly payroll. NHS trusts mostly buy through procurement frameworks that have audit and capacity requirements, and price caps squeeze margins.
- **Phase 3 option:** a small private-sector temp pool (nursing homes) once there is cash flow, invoice finance and a compliance platform. Avoid NHS framework work until you have staff.
- **Watch-out:** international nurse recruitment must follow the DHSC Code of Practice. Never actively recruit from "red list" countries.

### 3.2 Engineering, construction and technical trades: **Both, weighted to perm, with contract for skilled roles only**
- **Perm:** project managers, site managers, quantity surveyors, design/M&E/electrical engineers, estimators, maintenance engineers. Fees typically run 15–25%.
- **Contract:** senior, skilled contractors (QS, PMs, commissioning engineers) paid through umbrella or limited company. Weekly margin income builds a recurring revenue base, and these contractors don't need the night-time shift cover that labourers do.
- **Avoid:** high-volume labour and general trades supply (labourers, CSCS-card day-rate gangs). Margins are thin, no-shows are common, it is operationally heavy, and it carries CIS and false self-employment risk.
- **Watch-out:** since April 2026 recruitment agencies can be liable for umbrella company PAYE/NIC failures. Only use accredited umbrellas (FCSA/Professional Passport) and do IR35 status checks for limited-company contractors where the client is medium or large.

### 3.3 Accounting and finance: **Perm, plus interim at the senior end**
- **Perm:** accounts assistants through to financial controllers and FDs, and practice roles (audit, tax). Fees are typically 15–25%. This is the classic perm market, and clients are comfortable with retained or exclusive searches at senior level.
- **Interim:** FDs, financial controllers and project accountants (system implementations, year-end, M&A). Day rates are high, there are few heads, and margins are good.
- **Avoid:** transactional temps (AP/AR clerks on hourly rates). The margin is low and the time cost is high.

### Summary

| Sector | Phase 1–2 | Phase 3+ | Fee model |
|---|---|---|---|
| Care & Medical | Perm | Private-sector temp pool | 15–20% perm; ~18–25% temp margin |
| Engineering & Construction | Perm + skilled contract | Larger contract book | 15–25% perm; £/hour or day margin |
| Accounting & Finance | Perm + senior interim | Retained search | 15–25% perm; day-rate margin |

*Fee ranges are typical UK market levels, not quotes. Set your own terms of business.*

---

## 4. Operating model: who does what

| Task | AI assistants | Tristan |
|---|---|---|
| Market mapping and lead lists (companies + decision-makers) | ✅ Automated from compliant sources | Approves targeting rules |
| Enrichment (company news, hiring signals, role context) | ✅ | — |
| Personalised email sequences (BD and candidate) | ✅ Draft, send and follow up | Approves templates and first batches; spot-checks |
| Reply handling, objection handling, booking | ✅ Classify, answer FAQs, send booking link | Takes over warm or complex threads |
| LinkedIn connection requests, DMs, InMail | ❌ (no compliant automation exists) | ✅ By hand, from a daily AI-prepared task list with drafted messages |
| LinkedIn / X / Instagram posting | ✅ Draft and schedule via official APIs | Approves weekly batch |
| Discovery calls, interviews, offers, negotiations | ❌ | ✅ |
| Candidate screening notes, CV formatting, shortlists | ✅ Drafts | ✅ Decides (no solely automated decisions on people; see §8) |
| Morning standup | ✅ Prepares the brief | ✅ Reads, approves, redirects |

**The booking line** (honest version of what you described):
> "Thanks, Sarah. I've passed your details to Tristan, our Head of Recruitment, who'd like to speak with you personally. You can pick a time that suits you here: [Calendly link]. — Ava, AI Recruitment Assistant, Wrenfield Care"

The Calendly event sits on Tristan's calendar, so every booking lands with him automatically, already enriched with the CRM record.

---

## 5. System architecture

```
                    ┌────────────────────────────────────────────────┐
  LEAD SOURCES      │  Apollo API · Companies House API · CQC API     │
  (compliant)       │  Contracts Finder / Find a Tender · Adzuna API  │
                    │  Job-board CV databases (per board T&Cs)        │
                    │  Inbound: website forms, CV uploads, Calendly   │
                    └───────────────┬────────────────────────────────┘
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  CRM (Postgres / Supabase)                                            │
│  Companies · Contacts · Candidates · Jobs · Placements · Activities  │
│  Sequences · Consent & suppression · Content calendar · Tasks         │
└──────┬─────────────┬───────────────┬─────────────────┬──────────────┘
       ▼             ▼               ▼                 ▼
 ┌──────────┐  ┌────────────┐  ┌─────────────┐  ┌───────────────┐
 │ AI agent │  │ Email      │  │ Calendar    │  │ Content engine│
 │ workers  │  │ engine     │  │ Calendly +  │  │ blog + social │
 │ (Claude  │  │ (Instantly/│  │ Google Cal  │  │ scheduler     │
 │  API)    │  │ Smartlead) │  │ webhooks    │  │ (official APIs│
 └────┬─────┘  └─────┬──────┘  └──────┬──────┘  └──────┬────────┘
      └──────────────┴────────┬───────┴────────────────┘
                              ▼
                ┌──────────────────────────────┐
                │ Tristan's cockpit            │
                │ Morning standup · approvals  │
                │ LinkedIn task list · pipeline│
                └──────────────────────────────┘
```

### 5.1 CRM
- **Recommendation:** a custom, lightweight CRM on **Supabase** (Postgres, auth, storage, row-level security) with a Next.js admin UI. You own the data model, AI workers read and write it directly, and it costs very little. The CRM/outreach thread is building this.
- **Fallback if speed matters more than control:** an off-the-shelf recruitment CRM with an API (e.g. Recruit CRM, Loxo, Vincere), with the AI workers integrating through that API.
- **Key fields for personalisation:** role, seniority, company size, sector, recent company news, hiring signals (live job ads, contract wins, CQC rating changes, funding), shared context (location, qualifications), source and lawful basis, consent/opt-out status, last touch, sequence stage.
- **Non-negotiables:** source and lawful-basis recorded on every person, a global suppression list checked before any send, and data retention rules (e.g. auto-review candidates with no activity after 24 months).

### 5.2 Lead sources (no scraping)
| Source | Use | Notes |
|---|---|---|
| **Apollo.io** (API) | B2B decision-makers and work emails | Main BD data source; verify emails before sending |
| **LinkedIn Sales Navigator** (by hand) | Account and lead research, InMail | Tristan only. No extensions that automate or scrape it |
| **Companies House API** (free) | New companies, growth, officer changes, filings | Strong for Finance (new FD needs, year-ends) |
| **CQC API** (free) | Every registered care provider in England, ratings, new registrations | Gold for Care. New services and "requires improvement" ratings both signal hiring need |
| **Contracts Finder / Find a Tender** (free) | Public contract awards | Construction/engineering firms that just won work will need staff |
| **Adzuna API / Reed API** | Live job ads as hiring signals | Identify companies actively hiring; pitch them candidates |
| **Job-board CV databases** (CV-Library, Reed, Totaljobs, Indeed) | Candidate sourcing | Use within each board's terms. Contact candidates about relevant roles |
| **Inbound** | Website applications, CV drops, blog sign-ups, Calendly | The long-term goal: make outbound less necessary |

### 5.3 Email outreach engine
- **Sending platform:** Instantly or Smartlead (both have APIs, inbox rotation, warm-up and reply detection). The CRM pushes contacts and personalised copy in, and webhooks push replies, opens and bounces back. Building a raw sender in-house is not worth it at this scale.
- **Domains:** never cold-email from the main brand domains. Buy 2–3 secondary domains per brand (e.g. `wrenfieldcare.com`, `getwrenfieldcare.com`) that redirect to the main site. Each gets 2–3 Google Workspace or Microsoft 365 inboxes with SPF, DKIM and DMARC set up.
- **Warm-up and volume:** warm up for 2–3 weeks. Then send about 30–40 emails per inbox per day. 3 brands × 3 domains × 2 inboxes is roughly 500–700 sends per day at full capacity, which is plenty.
- **Personalisation:** the AI writes a first line and a value proposition from CRM data (company news, a relevant candidate, a market stat), using approved templates per sector and persona. Keep to 3–4 step sequences, plain text, one clear ask.
- **Hygiene:** verify emails before sending, keep bounces under 2%, include an unsubscribe line in every email, honour opt-outs within 24 hours globally across all brands, and include company details in the signature.

### 5.4 AI agent workers
- **Model:** Claude via the Anthropic API. A Sonnet-class model for writing and research, and a Haiku-class model for high-volume classification (reply intent, lead scoring).
- **Runtime:** scheduled jobs (Supabase Edge Functions + cron, or a small worker on Railway/Fly.io). Steps are idempotent, every action is logged to the CRM's activity table, and there is a daily send budget per agent.
- **Jobs:**
  1. *Prospecting* (nightly): pull new signals, score accounts, find decision-makers, enrich, add to sequences.
  2. *Writing* (per contact): draft personalised copy, and queue it for approval during the first weeks.
  3. *Inbox* (every 5–10 minutes): classify replies (interested / not now / referral / unsubscribe / out of office), answer simple ones, book meetings, escalate the rest.
  4. *LinkedIn prep* (daily): produce Tristan's list of ~20 people to connect with or message, with drafted notes.
  5. *Content* (weekly): draft blog posts and social posts.
  6. *Standup* (07:30 weekdays): see 5.6.
- **Guardrails:** human approval mode switchable per sequence, a blocklist of topics (no salary promises, no guaranteed placements), "AI assistant" disclosure in every signature, and a hard stop on contacting anyone on the suppression list.

### 5.5 Calendar and booking
- **Calendly** connected to Tristan's Google or Microsoft calendar, with separate event types: *Client discovery call (20 min)*, *Candidate intro call (15 min)*, *Senior search consultation (30 min)*.
- Calendly webhooks create or update the CRM record, attach the AI's research brief to the calendar invite, and stop that person's sequence.
- The assistants get read-only free/busy access to Tristan's calendar so they can propose times in replies.

### 5.6 Morning standup
Every weekday at 07:30 the agents compile a brief and deliver it to Tristan (email, or a thread in this project via a scheduled routine):
- Yesterday: sends, replies, positive replies, meetings booked, bounces and opt-outs, per brand.
- Today: Tristan's calls, each with a one-paragraph brief on the person and company.
- Decisions needed: copy or sequence approvals, new targeting ideas, warm threads to take over.
- LinkedIn task list: who to connect with and drafted messages.
- Content: posts scheduled today, and the blog draft awaiting approval.

Tristan replies with decisions in plain English ("pause Finance sequence 2", "target care homes in Kent next"), and the agents apply them.

### 5.7 Websites
- **Stack:** Next.js monorepo on Vercel, one codebase producing four sites (group + 3 sectors) with shared components and per-brand themes. Use a headless CMS (Sanity) or MDX for blogs and jobs.
- **Each sector site:** client/candidate toggle on the homepage, live jobs with "apply with CV", Calendly embeds, blog with persistent "join / book a call / get salary guide" prompts, salary guide lead magnets (email capture), team page, compliance pages (privacy notice, cookie consent, terms of business).
- **Group site:** the three divisions, leadership, memberships (e.g. REC, once joined), "book a call".
- **SEO:** sector + location landing pages (e.g. "Registered nurse jobs in Manchester"), structured data for job postings (Google for Jobs), and a fast, mobile-first build. The websites thread is building this.

### 5.8 Social content automation
| Channel | How to automate compliantly | Content |
|---|---|---|
| LinkedIn company pages (×4) | Official API via a scheduler (Buffer, Hootsuite or a custom tool built on LinkedIn's Community Management API) | Market updates, jobs, salary insights, placements |
| Tristan's personal LinkedIn | Scheduled posts via an approved scheduler. **Commenting, connecting and DMs stay manual** | Thought leadership: the highest-reach channel you have |
| X / Twitter | Official X API (paid tier) or a scheduler | Short takes, job links, blog threads |
| Instagram (later) | Instagram Graph API with a business account | Short video (e.g. Higgsfield), carousels, day-in-the-life and salary tips |
| AI assistants | **No personal LinkedIn profiles.** They appear on company pages, websites and email | — |

**Pipeline:** each week the AI turns one blog post into ~10 social posts across channels, mixing formats (carousel, poll, short video script, text post). Tristan approves the batch in one sitting, and the scheduler publishes. Every post links back to a landing page with a call to action.

---

## 6. Compliance framework (UK)

| Area | What it means here |
|---|---|
| **UK GDPR + DPA 2018 (as amended by the Data (Use and Access) Act 2025)** | Register with the ICO and pay the data protection fee. Use legitimate interests for B2B and candidate sourcing, with a documented LIA. Send a privacy notice to anyone you've sourced within one month. Honour access and erasure requests. Sign DPAs with every vendor (Apollo, Instantly, Supabase, Anthropic). Keep a records-of-processing log |
| **PECR** | Cold B2B email to *corporate* addresses (name@company.co.uk) is allowed with a clear opt-out. Email to *personal* addresses (gmail etc.) for marketing needs consent. So BD sequences go only to work emails, and candidate approaches should be about a specific relevant role, sent with an opt-out |
| **CAN-SPAM** | Only relevant if emailing US contacts. Include a physical address and opt-out anyway, since it's good practice |
| **Automated decisions (UK GDPR Art. 22 as amended)** | AI may rank and summarise, but **Tristan makes every decision** to reject or shortlist a candidate. Tell candidates that AI assists you, in the privacy notice |
| **Equality Act 2010** | Bias-test AI screening and outreach prompts. Never filter on protected characteristics or proxies for them (age from graduation year, name, etc.) |
| **Employment Agencies Act 1973 + Conduct Regulations 2003** | Written terms of business with clients before introductions. No fees charged to candidates. Agree terms with work-seekers. Suitability checks |
| **Temp and contract (when started)** | Key Information Document for every agency worker, Agency Workers Regulations, holiday pay, IR35 status determinations, umbrella due diligence (agency liability from April 2026), CIS for construction |
| **Sector checks** | Care: enhanced DBS, right to work, NMC/HCPC register checks, references, and following NHS Employment Check Standards as best practice. Construction: CSCS/CPCS cards, right to work. Finance: qualification verification (ACCA/CIMA/ICAEW) |
| **LinkedIn and platform terms** | No scraping, no browser-automation tools (e.g. "LinkedIn automation" extensions), no fake profiles. Use APIs and schedulers only for posting |
| **AI transparency** | Assistants are always named as AI in signatures, on the website and in replies if asked |
| **Business basics** | Limited company, business bank account, professional indemnity + employer's liability + public liability insurance, REC membership (credibility; the REC Code of Professional Practice), standard terms of business, privacy and cookie policies |

*This is a practical framework, not legal advice. Have a recruitment-specialist solicitor review your terms of business and privacy notice before launch (a fixed-fee package is common).*

---

## 7. Recommended tech stack

| Layer | Pick | Approx. monthly cost |
|---|---|---|
| Code & cross-device access | GitHub (private monorepo) | £0–£4 |
| Websites | Next.js + Vercel + Sanity | £0–£20 |
| CRM / database | Supabase | £0–£25 |
| AI | Anthropic API (Claude) | £50–£200, depending on volume |
| Lead data | Apollo.io | £40–£100 |
| LinkedIn research | Sales Navigator Core | ~£70–£80 |
| Email sending + warm-up | Instantly or Smartlead | £30–£100 |
| Mailboxes | Google Workspace (≈6–9 outreach inboxes + main) | £50–£100 |
| Domains | ~12 domains (4 brand + ~9 outreach) | ~£10 (annualised) |
| Booking | Calendly Standard | ~£10 |
| Social scheduling | Buffer or similar | £0–£40 |
| X API | Basic tier (only if direct API needed) | £0–£150 |
| Job boards (as needed) | CV-Library / Reed / Totaljobs | Varies; buy per campaign |
| **Indicative total** | | **≈ £350–£850 / month** before job-board spend and insurance |

*Prices are approximate as of 2026 and change often. Check current pricing before buying.*

**Accessing it from any computer:** everything lives in claude.ai (this project), GitHub (code) and cloud SaaS (CRM, email, calendar). Signing in on your laptop is enough. Nothing needs copying into a local `.claude` folder.

---

## 8. Roadmap

| Phase | Weeks | Deliverables |
|---|---|---|
| **0. Foundations** | 1–2 | Company formation and bank, ICO registration, insurance, final brand names, domains bought, Google Workspace, SPF/DKIM/DMARC, outreach inbox warm-up started, Calendly set up, terms of business and privacy notice drafted |
| **1. Shopfront** | 2–5 | Group + 3 sector websites live (jobs, blog, booking, CV upload), LinkedIn company pages, Tristan's profile refresh, first 8 blog posts and 2 salary guides |
| **2. Engine** | 4–8 | CRM live, Apollo/CQC/Companies House/Contracts Finder ingestion, AI writing + inbox workers, Instantly integration, Calendly → CRM, morning standup. Run in approval mode |
| **3. Scale** | 8–12 | Approval mode loosened for proven sequences, full social pipeline across LinkedIn and X, A/B testing of copy, Sales Navigator LinkedIn routine, first placements |
| **4. Expand** | 3–6 months | Contract desk (engineering, finance interim), Instagram + short video (Higgsfield), retained search offer, REC membership, private-sector care temp pool once cash flow allows |

**Year-one targets to steer by (illustrative):** 15–25 discovery calls per month by month 3, and 1–2 perm placements per month by month 4–6. At an average £40k salary and an 18% fee, each perm placement is about £7,200.

---

## 9. Decisions for Tristan

1. **Market:** confirm UK (England-first). Recommended.
2. **Brand names:** ✅ decided 16 Oct 2026: Wrenfield Talent Group, Wrenfield Finance, Wrenfield Care, Wrenfield Build (see §2).
3. **Launch order:** ✅ decided 16 Oct 2026: **Wrenfield Finance only**, with one website and one email address. Care and Build are parked. Finance wins for a solo recruiter because it is perm-led with high fees, needs no shift cover or weekly payroll, has light compliance, and its candidates and hiring managers live on LinkedIn. The lean plan is in [finance-launch-plan.md](finance-launch-plan.md); it replaces the multi-brand roadmap in §8 for the first 90 days.
4. **CRM:** custom (Supabase) or off-the-shelf? Recommended: custom.
5. **AI assistant names and avatars:** pick names and a visual style.
