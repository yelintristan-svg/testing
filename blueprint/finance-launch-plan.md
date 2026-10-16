# Wrenfield Finance: lean launch plan

*Version 1 · 16 Oct 2026 · Owner: Tristan*

One agency, one website, one email address, one recruiter. Wrenfield Care and Wrenfield Build stay parked until Finance is placing people regularly. This plan replaces the multi-brand roadmap in [business-blueprint.md](business-blueprint.md) §8 for the first 90 days.

---

## 1. Why Finance first

| | Accounting & Finance | Nursing & Care | Engineering & Construction |
|---|---|---|---|
| How you get paid | Perm fees, 15–25% of £35k–£90k salaries | Perm fees are lower; the money is in temp shifts | Mostly contract day-rate margin; perm for engineers |
| What it needs from one person | Calls, shortlists, offers in office hours | 24/7 shift cover and a weekly payroll you fund | Contractor payroll, IR35 and umbrella checks |
| Compliance per placement | Light: right to work, qualification and reference checks | Heavy: enhanced DBS, NMC/HCPC, training files | Medium: cards, tickets, CIS, umbrella liability since April 2026 |
| Where the people are | LinkedIn, heavily. Accountants and finance leaders keep profiles current | Job boards and word of mouth | Job boards, site networks |
| Future value | Qualified, business-partnering and systems roles keep growing; interim and retained search come later | Large, steady demand | Follows the construction cycle |

Finance is the best fit for a solo recruiter with a year's experience: high fees per placement, no out-of-hours work, no cash tied up in payroll, and a market that lives on LinkedIn, which is where you want to work.

**Focus inside Finance:** qualified and part-qualified accountants (ACCA, CIMA, ACA) into SMEs and PE-backed businesses, from management accountant up to financial controller, plus finance leaders as clients. Avoid transactional AP/AR clerk roles: low fees, and the jobs most exposed to automation.

---

## 2. Names and domains

| Brand | Status | Domain |
|---|---|---|
| **Wrenfield Finance** | Launching | wrenfieldfinance.co.uk (website and your inbox) |
| Wrenfield Care | Parked | wrenfieldcare.co.uk (buy now only if cheap, to hold it) |
| Wrenfield Build | Parked | wrenfieldbuild.co.uk (as above) |
| Wrenfield Talent Group | Parked | wrenfieldtalent.co.uk (as above) |
| Outreach domain | Optional, see §4 | wrenfieldfinance.com, redirected to the website |

The company can be one limited company, **Wrenfield Talent Ltd**, trading as Wrenfield Finance. That keeps the door open for the other two brands without a second company.

Before buying anything, check that "Wrenfield" is free at Companies House, on the UKIPO trade mark register (classes 35 and 41), and as domains. If it isn't, the fallback is **Ashcombe**, used the same way.

---

## 3. What goes live

1. **One website:** the Wrenfield Finance site in `websites/`. `config.js` has `live: ['finance']`, so the finance site never links to the parked brands. Run `node build.js` and upload `dist/finance/` to a free host (Cloudflare Pages or Netlify). Fill in the `← SWAP` fields first: your full name, LinkedIn URL, Calendly link, form endpoint (Formspree free tier), company number and address.
2. **One email address:** `tristan@wrenfieldfinance.co.uk` on Google Workspace (§4).
3. **One booking link:** Calendly free plan, one "15 minute intro call" event on your calendar.
4. **Your LinkedIn profile:** headline "Accounting & Finance Recruiter | Wrenfield Finance", the website in your featured section, and a Wrenfield Finance company page.
5. **The CRM** on your laptop, sending nothing itself (§5).

Parked until Finance makes 2+ placements a month for two months in a row: the group site, Care and Build sites, the AI assistant mailboxes, Instantly/Smartlead, multiple outreach domains, and social scheduling.

---

## 4. Email: use a business mailbox, not your personal address

**Recommendation:** one Google Workspace Business Starter mailbox (about £7 a month) on `wrenfieldfinance.co.uk`, with SPF, DKIM and DMARC switched on. That's your one email address for everything.

**Optional, about £10 a year:** buy `wrenfieldfinance.com`, redirect it to the website, and add it to the same Workspace account as a secondary domain so `tristan@wrenfieldfinance.com` lands in the same inbox. Send cold first emails from the .com and use the .co.uk for clients and candidates you already know. If a cold campaign ever gets marked as spam, your main address isn't the one that suffers. At 20 emails a day this is cheap insurance rather than a must; it becomes essential if you ever move to software sending hundreds a day.

**Why not your personal Gmail or Outlook**, even to save money:

- **You could lose your personal account.** Google's and Microsoft's consumer terms aren't written for business prospecting, and cold emails get spam reports. Enough reports and the provider limits or suspends the account, along with your personal email, photos and logins.
- **Deliverability is worse.** You can't add SPF, DKIM or DMARC to gmail.com for your business, so receiving servers can't verify that mail came from Wrenfield Finance. Business mail from a free address is more likely to go to spam, especially at company mail servers.
- **It looks less credible.** A finance director deciding whether to trust you with a £60k hire notices `@gmail.com`. Your own domain matches the website and the LinkedIn profile.
- **It makes GDPR harder.** You're the data controller for every prospect you email. Their details and your conversations should sit in a business system you can search, export and delete from when someone asks for their data or asks to be forgotten, not mixed into your personal inbox. It also makes it simple to hand over or add a colleague later.
- **PECR wants the sender to be clear.** Every marketing email has to identify who sent it and offer a simple opt-out. A branded address and signature do the first part naturally.

The CRM refuses a personal address as a sender (`add-assistant` rejects gmail.com, outlook.com and similar), so this can't happen by accident.

**Honest risk level:** at 20 personalised, hand-sent emails a day the deliverability risk from your personal address is modest, and the volume itself isn't the problem. The account, credibility and data-handling points are the reason to spend the £7 a month.

**Warm-up:** for the first two weeks, send 5–10 a day, then 20. Ask a few friends to reply to emails from the new address in week one.

---

## 5. The daily routine (about an hour)

The CRM does the finding, checking and drafting. You do the searching, sending and talking.

**1. Note 20–30 people while you browse LinkedIn (15 min).** Use LinkedIn search (or Sales Navigator later) by hand: finance directors, financial controllers and heads of finance at 20–250 person firms in your area, plus accountants for live roles. Add each one to a text file, one per line:

```
Jane Smith | Financial Controller | Acme Ltd | linkedin.com/in/janesmith | acme.co.uk | new FD joined in May
```

Name and profile URL are required; title, company, company website and your one-line reason make the drafts far better. Or build the list in **Apollo** (free tier) and export it as CSV: Apollo includes verified work emails where it has them.

**2. Load the list and build today's list (2 min).**

```bash
cd crm
python3 -m crm targets today.txt --brand finance --kind client
python3 -m crm daily --out today.md
```

`daily` then:
- looks up a work email for each new person through **Apollo or Hunter** (`CRM_EMAIL_PROVIDER`, your API key in an environment variable). It keeps only addresses the provider has **verified** and that are on the **company's own domain**. Personal addresses, guesses and other domains are dropped;
- runs the PECR and GDPR checks: suppression list, corporate address only, source recorded, and an Article 14 line in the first email saying where the details came from;
- drafts follow-ups that are due, then first emails for new people, until there are 20;
- lists up to 20 LinkedIn invitations, people without an email first, each with a connection note under 200 characters and a message for after they accept.

**3. Send the 20 emails from your own mailbox (30 min).** `today.md` has each email ready, with an "Open in your mail app" link that fills in the address, subject and body. Read it, tweak it, send it. Then log them:

```bash
python3 -m crm sent
```

The follow-ups (day 4, then day 11) come back onto future lists automatically. Anyone who replies gets taken off: log replies with `python3 -m crm reply <email> "<subject>" "<text>"`, and an "unsubscribe" reply suppresses them across every brand.

**4. Send the LinkedIn invitations by hand (10 min).** Open each profile from `today.md` and connect. Free accounts get only a handful of personalised notes a month, so use notes on your best 1–2 and send the rest without one. Log it with `python3 -m crm li invited <id> <id> ...`, then `accepted` when they accept and send the drafted message. People who share their email on LinkedIn can be added with `python3 -m crm add-contact --consent-at <now>`.

Settings for this routine (put them in a local `.env`, never in git):

```bash
CRM_DB=crm.sqlite3
CRM_UNSUB_MODE=reply          # opt-out by reply until the unsubscribe page is hosted
CRM_EMAIL_PROVIDER=apollo     # or hunter
APOLLO_API_KEY=...            # or HUNTER_API_KEY=...
CRM_LLM=claude                # better drafts; needs ANTHROPIC_API_KEY. 'offline' uses templates
CRM_DAILY_EMAILS=20
```

One-off setup: `python3 -m crm add-assistant tristan "Tristan" tristan@wrenfieldfinance.co.uk https://calendly.com/<you>/intro --brand finance --human` and `python3 -m crm load-sequences sequences/finance_*.json`.

---

## 6. Why no LinkedIn scraping or automation

LinkedIn profiles being publicly visible doesn't make scraping them allowed:

- **LinkedIn's User Agreement bans it.** No scrapers, bots, browser extensions that automate invitations or messages, or "ContactOut-style" tools that harvest data from profiles. LinkedIn detects this and restricts or permanently bans the account. Your personal profile, its network and history are the most valuable asset this business has.
- **UK GDPR still applies to public data.** Scraped data has no clear source or lawful basis, and the ICO and other regulators have said publicly that mass scraping of personal data from social sites can be unlawful. Apollo and Hunter sell business contact data under their own terms, with data processing agreements, and they tell you where it came from, which you need for the Article 14 notice.
- **Automation tools max out invitations, which is what gets accounts flagged.** LinkedIn caps invitations at roughly 100 a week. The CRM keeps you at 20 a day and 80 a week, sent by you.

What the CRM does instead is take away the slow parts: finding the email, checking it's lawful to use, drafting the message and remembering the follow-ups.

---

## 7. Before the first email (week 1–2)

- [ ] Check the name (Companies House, UKIPO, domains); buy `wrenfieldfinance.co.uk` (+ `.com` if you want the outreach domain)
- [ ] Form Wrenfield Talent Ltd; open a business bank account
- [ ] Register with the ICO and pay the data protection fee (tier 1, about £50–60 a year)
- [ ] Google Workspace mailbox with SPF, DKIM and DMARC; start warm-up
- [ ] Privacy notice on the website and a short legitimate interests assessment (the CRM's brand record has a starting summary)
- [ ] Terms of business for clients: fee (start at 18–20%), rebate period, payment terms. A recruitment solicitor's fixed-fee pack is worth it
- [ ] Professional indemnity insurance
- [ ] Website live, Calendly connected, LinkedIn profile updated
- [ ] Apollo free account (and/or Hunter); API key in `.env`

---

## 8. Monthly costs at launch

| Item | Cost |
|---|---|
| Google Workspace, 1 mailbox | ~£7 / month |
| Domains (1–2) | ~£10–25 / year |
| Website hosting (Cloudflare Pages or Netlify) | £0 |
| Calendly free plan | £0 |
| Apollo or Hunter free tier | £0 (paid plans from ~£40 / month when you need more lookups) |
| Anthropic API for drafts (optional) | ~£5–20 / month at 20 emails a day |
| ICO fee | ~£50–60 / year |
| Professional indemnity insurance | varies; get quotes |
| **Total before insurance** | **under £40 / month** |

LinkedIn Premium or Sales Navigator (about £30–80 a month) is worth trying in month two if free search limits or the note limit start to slow you down.

---

## 9. First 90 days

| When | Aim |
|---|---|
| Weeks 1–2 | Setup checklist done; warm-up at 5–10 emails a day; 20 LinkedIn invitations a day |
| Weeks 3–6 | 20 emails a day; 5–8 client calls a month; first 2–3 roles on |
| Weeks 7–12 | 10+ client calls a month; first placement (at £45k and 20%, that's £9,000) |
| Review at day 90 | Two placements a month two months running? Then unpark Wrenfield Care, or add AI-assisted sending for Finance |

Weekly numbers to watch, which the morning standup (`python3 -m crm standup`) reports: emails sent, reply rate (aim for 5–10%), calls booked, LinkedIn acceptance rate, and roles taken on.

*This is a practical plan, not legal advice. Have the terms of business, privacy notice and legitimate interests assessment checked before going live.*
