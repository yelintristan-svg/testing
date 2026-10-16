#!/usr/bin/env node
// Zero-dependency static site builder.
//   node build.js            → dist/<site>/ with production cross-site links (config urls)
//   node build.js --local    → cross-site links are relative, so dist/ can be browsed locally
const fs = require('fs');
const path = require('path');
const cfg = require('./config');

const LOCAL = process.argv.includes('--local');
const ROOT = __dirname;
const DIST = path.join(ROOT, 'dist');
const SECTORS = ['care', 'build', 'finance'];
const ALL = ['group', ...SECTORS];
// Sites that are live (config.live). A live page never links to a parked site.
const LIVE = new Set(cfg.live || ALL);
const isLive = (k) => LIVE.has(k);
const groupLive = () => isLive('group');
const partOf = () => (groupLive() ? ` Part of ${cfg.sites.group.name}.` : '');

// ── helpers ──────────────────────────────────────────────────
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const write = (file, html) => { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, html); };
const fmtDate = (d) => new Date(d + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
const initials = (n) => n.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();

// Link to another site's page. `rel` is the path back to the current site root.
function siteLink(key, page, rel) {
  page = page || 'index.html';
  if (LOCAL) return `${rel}../${key}/${page}`;
  return `${cfg.sites[key].url.replace(/\/$/, '')}/${page === 'index.html' ? '' : page}`;
}

// Tiny Markdown → HTML (headings, lists, quotes, paragraphs, bold, italics, links).
function inline(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*(?!\s)(.+?)\*/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>');
}
function markdown(md) {
  return md.trim().split(/\n\s*\n/).map((block) => {
    const lines = block.split('\n');
    const h = block.match(/^(#{2,4})\s+(.*)$/);
    if (h && lines.length === 1) return `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`;
    if (lines.every((l) => /^\s*[-*]\s+/.test(l))) return `<ul>${lines.map((l) => `<li>${inline(l.replace(/^\s*[-*]\s+/, ''))}</li>`).join('')}</ul>`;
    if (lines.every((l) => /^\s*\d+\.\s+/.test(l))) return `<ol>${lines.map((l) => `<li>${inline(l.replace(/^\s*\d+\.\s+/, ''))}</li>`).join('')}</ol>`;
    if (lines.every((l) => /^>\s?/.test(l))) return `<blockquote>${inline(lines.map((l) => l.replace(/^>\s?/, '')).join(' '))}</blockquote>`;
    return `<p>${inline(lines.join(' '))}</p>`;
  }).join('\n');
}

function loadPosts(key) {
  const dir = path.join(ROOT, 'content', 'blog', key);
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter((f) => f.endsWith('.md')).map((f) => {
    const raw = fs.readFileSync(path.join(dir, f), 'utf8');
    const m = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
    if (!m) throw new Error(`Missing frontmatter in ${key}/${f}`);
    const meta = Object.fromEntries(m[1].split('\n').filter(Boolean).map((l) => {
      const i = l.indexOf(':');
      return [l.slice(0, i).trim(), l.slice(i + 1).trim().replace(/^["']|["']$/g, '')];
    }));
    return { ...meta, audience: meta.audience || 'both', slug: f.replace(/\.md$/, ''), html: markdown(m[2]), site: key };
  }).sort((a, b) => b.date.localeCompare(a.date));
}

// ── shared layout ────────────────────────────────────────────
function head(key, { title, description, rel, canonical, type = 'website' }) {
  const s = cfg.sites[key];
  const url = `${s.url.replace(/\/$/, '')}/${canonical || ''}`;
  const org = {
    '@context': 'https://schema.org', '@type': 'EmploymentAgency', name: s.name, url: s.url,
    email: s.email, telephone: s.phone, address: cfg.company.address,
    parentOrganization: key === 'group' || !groupLive() ? undefined : { '@type': 'Organization', name: cfg.sites.group.name, url: cfg.sites.group.url },
    sameAs: Object.values(cfg.social),
  };
  return `<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<link rel="canonical" href="${esc(url)}">
<meta property="og:type" content="${type}">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:url" content="${esc(url)}">
<meta property="og:site_name" content="${esc(s.name)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="${rel}assets/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="${rel}assets/styles.css">
<style>:root{--accent:${s.accent};--accent-dark:${s.accentDark}}</style>
<script type="application/ld+json">${JSON.stringify(org)}</script>
</head>`;
}

function header(key, rel, active) {
  const s = cfg.sites[key];
  const isGroup = key === 'group';
  const links = isGroup
    ? [['Divisions', 'index.html#divisions'], ['How we work', 'index.html#how'], ['Insights', 'blog/index.html'], ['Contact', 'contact.html']]
    : [['Hire staff', 'hire.html'], ['Find work', 'register.html'], ['How we work', 'index.html#model'], ['Insights', 'blog/index.html']];
  const nav = links.map(([t, h]) => `<a href="${rel}${h}"${active === h ? ' class="active"' : ''}>${t}</a>`).join('');
  const groupLink = isGroup || !groupLive() ? '' : `<a href="${siteLink('group', 'index.html', rel)}">${esc(cfg.sites.group.short)} Group</a>`;
  return `<header class="site-header"><div class="wrap">
  <a class="logo" href="${rel}index.html"><span class="logo-mark">${esc(s.name[0])}</span>${esc(s.name)}</a>
  <button class="menu-btn" aria-label="Menu" aria-expanded="false">☰</button>
  <nav class="nav">${nav}${groupLink}<a class="btn btn-primary" href="${cfg.calendly[key]}" data-calendly="nav">Book a call</a></nav>
</div></header>`;
}

function footer(key, rel) {
  const s = cfg.sites[key];
  const divisions = SECTORS.filter((k) => isLive(k) && k !== key).map((k) => `<li><a href="${siteLink(k, 'index.html', rel)}">${esc(cfg.sites[k].name)}</a></li>`).join('');
  return `<footer class="site-footer"><div class="wrap">
  <div class="foot-grid">
    <div>
      <a class="logo" href="${rel}index.html" style="color:#fff"><span class="logo-mark">${esc(s.name[0])}</span>${esc(s.name)}</a>
      <p style="margin-top:14px">${esc(key === 'group' ? s.tagline : `Specialist ${s.sector.toLowerCase()} recruitment.${partOf()}`)}</p>
    </div>
    ${groupLive() || divisions ? `<div><h4>Group</h4><ul>${groupLive() ? `<li><a href="${siteLink('group', 'index.html', rel)}">${esc(cfg.sites.group.name)}</a></li>` : ''}${divisions}</ul></div>` : ''}
    <div><h4>Contact</h4><ul><li><a href="mailto:${s.email}">${s.email}</a></li><li><a href="tel:${s.phone.replace(/\s/g, '')}">${s.phone}</a></li><li><a href="${cfg.calendly[key]}" data-calendly="footer">Book a call</a></li></ul></div>
    <div><h4>Follow</h4><ul><li><a href="${cfg.social.linkedin}" rel="noopener">LinkedIn</a></li><li><a href="${cfg.social.twitter}" rel="noopener">X / Twitter</a></li><li><a href="${cfg.social.instagram}" rel="noopener">Instagram</a></li></ul></div>
  </div>
  <div class="foot-legal"><span>© ${new Date().getFullYear()} ${esc(cfg.company.legalName)} · Registered in England &amp; Wales No. ${esc(cfg.company.regNo)} · ${esc(cfg.company.address)}</span><a href="${rel}privacy.html">Privacy</a></div>
</div></footer>`;
}

// Sticky bar that keeps nudging visitors to join/book. Sector sites swap by audience.
function joinBar(key, rel) {
  if (key === 'group') {
    return `<div class="join-bar" role="complementary"><p><strong>Hiring or looking for work?</strong><span>Talk to a specialist in your sector.</span></p><a class="btn btn-primary" href="${cfg.calendly.group}" data-calendly="joinbar">Book a call</a><button class="x" aria-label="Dismiss">×</button></div>`;
  }
  return `<div class="join-bar" role="complementary">
  <p data-for="client"><strong>Need staff?</strong><span>15 minutes with ${esc(cfg.owner.name)} and you'll have a plan.</span></p>
  <p data-for="candidate"><strong>Looking for your next role?</strong><span>Register once, hear about jobs first.</span></p>
  <a data-for="client" class="btn btn-primary" href="${cfg.calendly[key]}" data-calendly="joinbar">Book a call</a>
  <a data-for="candidate" class="btn btn-primary" href="${rel}register.html">Register</a>
  <button class="x" aria-label="Dismiss">×</button></div>`;
}

function page(key, opts, bodyHtml) {
  const { rel, view, active } = opts;
  return `${head(key, opts)}
<body data-site="${key}"${view ? ` data-view="${view}"` : ''}>
${header(key, rel, active)}
<main>
${bodyHtml}
</main>
${footer(key, rel)}
${joinBar(key, rel)}
<script src="${rel}assets/main.js" defer></script>
</body>
</html>`;
}

// Reusable blocks
const hidden = (key, form) => `<input type="hidden" name="site" value="${key}"><input type="hidden" name="form" value="${form}"><input type="text" name="_gotcha" style="display:none" tabindex="-1" autocomplete="off">`;

function postCard(p, rel, hrefOverride) {
  const href = hrefOverride || `${rel}blog/${p.slug}.html`;
  const label = p.audience === 'client' ? 'For employers' : p.audience === 'candidate' ? 'For candidates' : 'For everyone';
  return `<a class="card post-card" href="${href}" data-audience="${p.audience}">
  <div class="meta"><span class="badge">${label}</span> · ${fmtDate(p.date)}</div>
  <h3>${esc(p.title)}</h3><p>${esc(p.excerpt)}</p><span class="more">Read →</span></a>`;
}

function alertsForm(key, rel, heading, sub, audience = '') {
  return `<div class="inline-cta">
  <h3>${esc(heading)}</h3><p class="muted">${esc(sub)}</p>
  <form class="inline-form" action="${cfg.formEndpoint}" method="POST" data-ajax>
    ${hidden(key, 'newsletter')}
    <input type="email" name="email" placeholder="you@email.com" required aria-label="Email">
    ${audience ? `<input type="hidden" name="audience" value="${audience}">` : ''}
    <button class="btn btn-primary" type="submit">Join</button>
  </form>
  <div class="form-ok">You're on the list. Look out for our next email.</div></div>`;
}

function founderBlock(key) {
  const o = cfg.owner;
  const blurb = key === 'group'
    ? `Every division is led personally by ${o.name}. One accountable person from first call to placement, backed by a sourcing and outreach team that finds people other agencies miss.`
    : `When you get in touch with ${cfg.sites[key].name}, you deal with ${o.name} directly. No being passed around a call centre, no junior consultant learning on your vacancy.`;
  return `<section><div class="wrap"><div class="card founder">
  <div class="avatar">${initials(o.name)}</div>
  <div><span class="eyebrow">Who you'll speak to</span><h2 style="margin-bottom:.2em">${esc(o.name)}</h2><p class="muted" style="font-weight:700">${esc(o.title)}, ${esc(groupLive() || !cfg.sites[key] ? cfg.sites.group.name : cfg.sites[key].name)}</p>
  <p class="muted">${esc(blurb)}</p>
  <div class="btn-row"><a class="btn btn-primary" href="${cfg.calendly[key]}" data-calendly="founder">Book time with ${esc(o.name)}</a><a class="btn btn-ghost" href="${o.linkedin}" rel="noopener">Connect on LinkedIn</a></div></div>
</div></div></section>`;
}

const STEPS = {
  client: [
    ['Quick call', 'Fifteen minutes on the role, the team, the budget and when you need someone.'],
    ['Targeted search', 'We go beyond job boards: direct, personal outreach to people who fit, including those not actively looking.'],
    ['Vetted shortlist', 'You see a small number of screened, compliant candidates with a note on why each one fits.'],
    ['Placed and followed up', 'We handle offers and start dates, then check in after the first weeks so it sticks.'],
  ],
  candidate: [
    ['Register', 'Two minutes: your role, location, availability and a CV if you have one handy.'],
    ['Quick chat', 'We learn what you actually want, including pay, hours, travel and the next step in your career.'],
    ['Matched roles', 'We only put forward jobs that fit, and never send your CV anywhere without asking.'],
    ['Start and grow', 'We support you through starting, and we are on hand for the next move too.'],
  ],
};

function faqs(key) {
  const s = { ...cfg.sites[key], key };
  return {
    client: [
      ['How do your fees work?', `Temporary and contract staff are charged at an agreed hourly or daily rate with no hidden extras. Permanent placements are a one-off fee as a percentage of first-year salary, with a rebate period if things don't work out. We'll give you exact numbers on the first call.`],
      ['How quickly can you supply?', `For temp and contract cover we match from people already vetted and available, so short notice is often possible. Permanent searches typically produce a shortlist within one to two weeks.`],
      ['What checks do you carry out?', s.key === 'care' ? 'Enhanced DBS, right to work, NMC/HCPC registration where relevant, mandatory training certificates and two references.' : s.key === 'build' ? 'Right to work, CSCS/CPCS and trade tickets, relevant qualifications and references from recent sites.' : 'Right to work, qualifications and membership checks (ACCA/CIMA/ICAEW), references and, where required, credit and DBS checks.'],
      ['Can we take a temp on permanently?', 'Yes. We agree clear temp-to-perm terms up front so there are no surprises.'],
    ],
    candidate: [
      ['Does it cost me anything?', 'Never. Employers pay our fees. Registering and working with us is free.'],
      ['Will you send my CV without asking?', 'No. We always talk to you about a role and get your OK before your details go to any employer.'],
      ['How and when do I get paid?', 'Temporary and contract workers are paid weekly. We will talk you through the options, rates and holiday pay before you start.'],
      ['What happens after I register?', `${cfg.owner.name} or a member of the team will be in touch, usually within one working day, to chat about what you're looking for.`],
    ],
  };
}

function faqBlock(list) {
  return list.map(([q, a]) => `<details><summary>${esc(q)}</summary><p>${esc(a)}</p></details>`).join('');
}

// ── SECTOR SITE PAGES ────────────────────────────────────────
function sectorHome(key, posts) {
  const s = { ...cfg.sites[key], key };
  const rel = '';
  const F = faqs(key);
  const view = (v) => {
    const c = s[v];
    return `<div data-for="${v}">
      <span class="eyebrow">${esc(c.eyebrow)}</span>
      <h1>${esc(c.h1)}</h1>
      <p class="lead">${esc(c.sub)}</p>
      <div class="btn-row">${v === 'client'
        ? `<a class="btn btn-primary" href="${cfg.calendly[key]}" data-calendly="hero">${esc(c.cta)}</a><a class="btn btn-ghost" href="hire.html">Send a vacancy</a>`
        : `<a class="btn btn-primary" href="register.html">${esc(c.cta)}</a><a class="btn btn-ghost" href="blog/index.html?for=candidate">Career advice</a>`}</div>
    </div>`;
  };
  const points = (v) => `<div class="grid-3" data-for="${v}">${s[v].points.map(([t, d], i) => `<div class="card"><div class="num">${i + 1}</div><h3>${esc(t)}</h3><p>${esc(d)}</p></div>`).join('')}</div>`;
  const steps = (v) => `<div class="grid-2" data-for="${v}" style="grid-template-columns:repeat(auto-fit,minmax(230px,1fr))">${STEPS[v].map(([t, d], i) => `<div class="card"><div class="num">${i + 1}</div><h3>${esc(t)}</h3><p>${esc(d)}</p></div>`).join('')}</div>`;

  const body = `
<section class="hero"><div class="wrap hero-grid">
  <div>
    <div class="toggle" role="group" aria-label="I am">
      <button data-set-view="client" aria-pressed="true">I'm hiring</button>
      <button data-set-view="candidate" aria-pressed="false">I'm looking for work</button>
    </div>
    ${view('client')}${view('candidate')}
  </div>
  <aside class="hero-card">
    <span class="eyebrow">${esc(s.sector)}</span>
    <h3>How we recruit</h3>
    <div class="model">${esc(s.model)}</div>
    <p class="muted" style="font-size:.95rem">${esc(s.modelWhy)}</p>
    ${groupLive() ? `<small>Part of ${esc(cfg.sites.group.name)}</small>` : ''}
  </aside>
</div></section>

<section class="alt"><div class="wrap">
  <div class="section-head"><span class="eyebrow">Why ${esc(s.name)}</span>
    <h2 data-for="client">Specialists in ${esc(s.sector.toLowerCase())}. Nothing else.</h2>
    <h2 data-for="candidate">A recruiter who knows your world.</h2>
  </div>
  ${points('client')}${points('candidate')}
</div></section>

<section><div class="wrap">
  <div class="section-head"><span class="eyebrow">Roles</span>
    <h2 data-for="client">Who we place</h2><h2 data-for="candidate">Roles we recruit for</h2></div>
  <div class="chips">${s.client.roles.map((r) => `<span class="chip">${esc(r)}</span>`).join('')}</div>
</div></section>

<section class="alt" id="model"><div class="wrap">
  <div class="section-head"><span class="eyebrow">How it works</span><h2>Four steps, one point of contact.</h2></div>
  ${steps('client')}${steps('candidate')}
</div></section>

${founderBlock(key)}

<section class="alt"><div class="wrap">
  <div class="section-head"><span class="eyebrow">Insights</span><h2 data-for="client">Advice for employers</h2><h2 data-for="candidate">Career advice</h2></div>
  <div class="post-grid">${posts.slice(0, 6).map((p) => postCard(p, rel)).join('')}</div>
  <p style="margin-top:28px"><a class="btn btn-ghost" href="blog/index.html">All articles →</a></p>
</div></section>

<section><div class="wrap grid-2" style="align-items:start">
  <div><span class="eyebrow">FAQ</span><h2>Common questions</h2>
    <div data-for="client">${faqBlock(F.client)}</div><div data-for="candidate">${faqBlock(F.candidate)}</div></div>
  <div>${alertsFormForView(key, rel)}</div>
</div></section>

<section style="padding-top:0"><div class="wrap">${ctaBand(key, rel)}</div></section>`;

  return page(key, {
    title: `${s.name} | ${s.sector} Recruitment`,
    description: `${s.name}: specialist ${s.sector.toLowerCase()} recruitment. ${s.model}. ${s.client.sub}`,
    rel, view: 'client', canonical: '',
  }, body);
}

function alertsFormForView(key, rel) {
  return `<div data-for="client">${alertsForm(key, rel, 'Hiring insights, monthly', 'Salary and rate benchmarks, market updates and hiring tips for your sector. One short email a month.', 'client')}</div>
  <div data-for="candidate">${alertsForm(key, rel, 'Get new jobs first', 'Join the list and we will email you new roles before they go on job boards.', 'candidate')}</div>`;
}

function ctaBand(key, rel) {
  if (key === 'group') {
    return `<div class="cta-band"><div><h2>Let's find your people.</h2><p>Book a 15-minute intro call. We will tell you honestly whether we can help, and how.</p></div>
    <div class="btn-row"><a class="btn btn-light" href="${cfg.calendly.group}" data-calendly="cta-band">Book a call</a></div></div>`;
  }
  return `<div class="cta-band" data-for="client"><div><h2>Got a role to fill?</h2><p>Book 15 minutes with ${esc(cfg.owner.name)}. You will leave the call with a plan, rates and a timeline.</p></div>
    <div class="btn-row"><a class="btn btn-light" href="${cfg.calendly[key]}" data-calendly="cta-band">Book a call</a></div></div>
  <div class="cta-band" data-for="candidate"><div><h2>Ready for your next role?</h2><p>Register in two minutes and hear about new jobs before anyone else.</p></div>
    <div class="btn-row"><a class="btn btn-light" href="${rel}register.html">Register now</a></div></div>`;
}

function hirePage(key) {
  const s = cfg.sites[key];
  const body = `
<section class="hero" style="padding-bottom:40px"><div class="wrap">
  <span class="eyebrow">For employers</span><h1>Tell us who you need.</h1>
  <p class="lead">Book a call straight into the diary, or send the details below and we will come back to you the same working day.</p>
</div></section>
<section style="padding-top:20px"><div class="wrap grid-2" style="align-items:start">
  <div class="card">
    <h3>Send a vacancy</h3>
    <form class="stack" action="${cfg.formEndpoint}" method="POST" data-ajax>
      ${hidden(key, 'vacancy')}
      <div class="row-2"><div class="field"><label>Your name</label><input name="name" required></div><div class="field"><label>Company</label><input name="company" required></div></div>
      <div class="row-2"><div class="field"><label>Work email</label><input type="email" name="email" required></div><div class="field"><label>Phone</label><input type="tel" name="phone"></div></div>
      <div class="row-2"><div class="field"><label>Role(s)</label><input name="role" placeholder="e.g. ${esc(s.client.roles[0])}" required></div><div class="field"><label>Location</label><input name="location"></div></div>
      <div class="row-2"><div class="field"><label>Type</label><select name="type"><option>Temporary / contract</option><option>Permanent</option><option>Not sure yet</option></select></div><div class="field"><label>Start</label><select name="start"><option>ASAP</option><option>Within a month</option><option>1–3 months</option><option>Just planning</option></select></div></div>
      <div class="field"><label>Anything else?</label><textarea name="notes" rows="4" placeholder="Hours, rate or salary, must-haves…"></textarea></div>
      <p class="consent">By sending this you agree to our <a href="privacy.html">privacy policy</a>.</p>
      <button class="btn btn-primary" type="submit">Send vacancy</button>
    </form>
    <div class="form-ok">Thanks, that's with us. ${esc(cfg.owner.name)} will be in touch shortly.</div>
  </div>
  <div class="card" style="padding:0;overflow:hidden">
    <div class="calendly-inline-widget" data-url="${cfg.calendly[key]}?hide_gdpr_banner=1&utm_source=website&utm_medium=${key}&utm_content=hire-page" style="min-width:300px;height:720px"></div>
    <script src="https://assets.calendly.com/assets/external/widget.js" async></script>
  </div>
</div></section>`;
  return page(key, { title: `Hire ${s.sector} staff | ${s.name}`, description: `Send a vacancy or book a call with ${s.name}. ${s.model}.`, rel: '', view: 'client', canonical: 'hire.html', active: 'hire.html' }, body);
}

function registerPage(key) {
  const s = cfg.sites[key];
  const body = `
<section class="hero" style="padding-bottom:40px"><div class="wrap">
  <span class="eyebrow">For candidates</span><h1>Register with ${esc(s.name)}</h1>
  <p class="lead">Two minutes, free, and your details are never shared without your permission.</p>
</div></section>
<section style="padding-top:20px"><div class="wrap grid-2" style="align-items:start">
  <div class="card">
    <form class="stack" action="${cfg.formEndpoint}" method="POST" enctype="multipart/form-data" data-ajax>
      ${hidden(key, 'candidate-registration')}
      <div class="row-2"><div class="field"><label>Full name</label><input name="name" required></div><div class="field"><label>Email</label><input type="email" name="email" required></div></div>
      <div class="row-2"><div class="field"><label>Mobile</label><input type="tel" name="phone" required></div><div class="field"><label>Town / postcode</label><input name="location" required></div></div>
      <div class="row-2"><div class="field"><label>Role you're looking for</label><input name="role" placeholder="e.g. ${esc(s.client.roles[1])}" required></div>
        <div class="field"><label>Work type</label><select name="type"><option>Temporary / contract</option><option>Permanent</option><option>Open to both</option></select></div></div>
      <div class="field"><label>LinkedIn profile (optional)</label><input type="url" name="linkedin" placeholder="https://linkedin.com/in/…"></div>
      <div class="field"><label>CV (optional)</label><input type="file" name="cv" accept=".pdf,.doc,.docx"></div>
      <div class="field"><label>Availability / notes</label><textarea name="notes" rows="3"></textarea></div>
      <label class="consent"><input type="checkbox" name="job_alerts" value="yes" checked> Email me new jobs that match.</label>
      <p class="consent">By registering you agree to our <a href="privacy.html">privacy policy</a>.</p>
      <button class="btn btn-primary" type="submit">Register</button>
    </form>
    <div class="form-ok">You're registered. ${esc(cfg.owner.name)} will be in touch, usually within one working day.</div>
  </div>
  <div>
    <h3>What happens next</h3>
    ${STEPS.candidate.map(([t, d], i) => `<div class="card" style="margin-bottom:14px"><div class="num">${i + 1}</div><h3>${esc(t)}</h3><p>${esc(d)}</p></div>`).join('')}
    <div data-for="candidate">${faqBlock(faqs(key).candidate)}</div>
  </div>
</div></section>`;
  return page(key, { title: `Register for ${s.sector} jobs | ${s.name}`, description: `Register with ${s.name} for temporary, contract and permanent ${s.sector.toLowerCase()} jobs.`, rel: '', view: 'candidate', canonical: 'register.html', active: 'register.html' }, body);
}

// ── BLOG (all sites) ─────────────────────────────────────────
function blogIndex(key, posts, extra = []) {
  const s = cfg.sites[key];
  const rel = '../';
  const isGroup = key === 'group';
  const body = `
<section class="hero" style="padding-bottom:40px"><div class="wrap">
  <span class="eyebrow">Insights</span><h1>${isGroup ? 'News & insights' : `${esc(s.sector)} insights`}</h1>
  <p class="lead">${isGroup ? 'Hiring advice, market updates and career guidance from across the group.' : 'Practical advice for employers and candidates, written by people who recruit in this sector every day.'}</p>
</div></section>
<section style="padding-top:20px"><div class="wrap">
  ${isGroup ? '' : `<div class="filter"><button data-filter="all" aria-pressed="false">All</button><button data-filter="client" aria-pressed="true">For employers</button><button data-filter="candidate" aria-pressed="false">For candidates</button></div>`}
  <div class="post-grid">${posts.map((p) => postCard(p, rel)).join('')}</div>
  ${extra.length ? `<h2 style="margin-top:64px">From our divisions</h2><div class="post-grid">${extra.map((p) => postCard(p, rel, siteLink(p.site, `blog/${p.slug}.html`, rel))).join('')}</div>` : ''}
  ${isGroup ? alertsForm(key, rel, 'Get our monthly briefing', 'The best of our insights from across care, construction and finance. One email a month.') : alertsFormForView(key, rel)}
</div></section>`;
  return page(key, { title: `Insights | ${s.name}`, description: `Recruitment advice, market updates and career guidance from ${s.name}.`, rel, view: isGroup ? null : 'client', canonical: 'blog/', active: 'blog/index.html' }, body);
}

function blogPost(key, p, posts) {
  const s = cfg.sites[key];
  const rel = '../';
  const isGroup = key === 'group';
  const view = p.audience === 'both' ? 'client' : p.audience;
  const related = posts.filter((x) => x.slug !== p.slug).slice(0, 3);
  // Mid-article and end-of-article prompts, matched to who the article is for.
  const promptFor = (aud) => {
    if (isGroup) return `<div class="inline-cta"><h3>Talk to a specialist</h3><p class="muted">Whether you're hiring or job hunting, a 15-minute call is the fastest way to see if we can help.</p><a class="btn btn-primary" href="${cfg.calendly.group}" data-calendly="article">Book a call</a></div>`;
    return aud === 'candidate'
      ? `<div class="inline-cta"><h3>Looking for ${esc(s.sector.toLowerCase())} work?</h3><p class="muted">Register once and we'll match you to roles that fit, often before they're advertised.</p><a class="btn btn-primary" href="${rel}register.html">Register free</a></div>`
      : `<div class="inline-cta"><h3>Need staff now?</h3><p class="muted">Book 15 minutes with ${esc(cfg.owner.name)} and get rates, availability and a plan.</p><a class="btn btn-primary" href="${cfg.calendly[key]}" data-calendly="article">Book a call</a></div>`;
  };
  const parts = p.html.split('\n');
  const mid = Math.max(2, Math.floor(parts.length / 2));
  const article = [...parts.slice(0, mid), promptFor(view), ...parts.slice(mid)].join('\n');
  const ld = { '@context': 'https://schema.org', '@type': 'BlogPosting', headline: p.title, datePublished: p.date, description: p.excerpt, author: { '@type': 'Person', name: p.author || cfg.owner.name }, publisher: { '@type': 'Organization', name: s.name } };
  const body = `
<section><div class="wrap">
  <article class="article">
    <header>
      <p><a href="index.html">← All insights</a></p>
      <span class="badge">${p.audience === 'client' ? 'For employers' : p.audience === 'candidate' ? 'For candidates' : 'For everyone'}</span>
      <h1 style="margin-top:14px;font-size:clamp(2rem,4vw,2.8rem)">${esc(p.title)}</h1>
      <p class="meta">${esc(p.author || cfg.owner.name)} · ${fmtDate(p.date)}</p>
    </header>
    <div class="prose">${article}</div>
    ${p.audience === 'both' && !isGroup ? promptFor('candidate') : ''}
    ${isGroup ? alertsForm(key, rel, 'Get our monthly briefing', 'Hiring and career insights from across the group.') : alertsFormForView(key, rel)}
  </article>
  ${related.length ? `<div style="max-width:var(--max);margin:64px auto 0"><h2>Keep reading</h2><div class="post-grid">${related.map((r) => postCard(r, rel)).join('')}</div></div>` : ''}
</div></section>
<script type="application/ld+json">${JSON.stringify(ld)}</script>`;
  return page(key, { title: `${p.title} | ${s.name}`, description: p.excerpt, rel, view: isGroup ? null : view, canonical: `blog/${p.slug}.html`, type: 'article', active: 'blog/index.html' }, body);
}

// ── GROUP SITE PAGES ─────────────────────────────────────────
function groupHome(posts, allSectorPosts) {
  const g = cfg.sites.group;
  const rel = '';
  const divisions = SECTORS.map((k) => {
    const s = cfg.sites[k];
    return `<a class="card division" style="--c:${s.accent}" href="${siteLink(k, 'index.html', rel)}">
      <span class="tag">${esc(s.model)}</span><h3 style="font-size:1.45rem">${esc(s.name)}</h3>
      <p class="muted" style="font-weight:700;margin-bottom:8px">${esc(s.sector)}</p><p>${esc(s.client.sub)}</p>
      <span class="go">Visit ${esc(s.name)} →</span></a>`;
  }).join('');
  const how = SECTORS.map((k) => {
    const s = cfg.sites[k];
    return `<div class="card" style="border-left:5px solid ${s.accent}"><h3>${esc(s.sector)}</h3><p style="font-weight:700;color:var(--ink);margin-bottom:8px">${esc(s.model)}</p><p>${esc(s.modelWhy)}</p></div>`;
  }).join('');
  const latest = [...posts.map((p) => postCard(p, rel)), ...allSectorPosts.slice(0, 3).map((p) => postCard(p, rel, siteLink(p.site, `blog/${p.slug}.html`, rel)))].slice(0, 6).join('');

  const body = `
<section class="hero"><div class="wrap hero-grid">
  <div>
    <span class="eyebrow">Specialist recruitment group</span>
    <h1>${esc(g.tagline)}</h1>
    <p class="lead">Three specialist agencies covering care and clinical, construction and engineering, and accounting and finance. Each one recruits the way its industry actually hires.</p>
    <div class="btn-row"><a class="btn btn-primary" href="${cfg.calendly.group}" data-calendly="hero">Book an intro call</a><a class="btn btn-ghost" href="#divisions">Find your sector</a></div>
  </div>
  <aside class="hero-card">
    <span class="eyebrow">Our divisions</span>
    ${SECTORS.map((k) => `<p style="margin:0 0 12px"><a href="${siteLink(k, 'index.html', rel)}" style="font-weight:800;color:${cfg.sites[k].accent};text-decoration:none">${esc(cfg.sites[k].name)} →</a><br><small>${esc(cfg.sites[k].sector)}</small></p>`).join('')}
  </aside>
</div></section>

<section class="alt" id="divisions"><div class="wrap">
  <div class="section-head"><span class="eyebrow">Divisions</span><h2>Three specialists. One standard.</h2><p class="muted">Pick your sector to see roles, how we work and how to get started, whether you are hiring or looking for work.</p></div>
  <div class="grid-3">${divisions}</div>
</div></section>

<section id="how"><div class="wrap">
  <div class="section-head"><span class="eyebrow">How we work</span><h2>Permanent or temporary? It depends on the industry.</h2><p class="muted">We don't force one model on every sector. Each division leads with the type of hiring its clients actually need.</p></div>
  <div class="grid-3">${how}</div>
</div></section>

<section class="alt"><div class="wrap">
  <div class="section-head"><span class="eyebrow">Why us</span><h2>Small enough to care. Built to move fast.</h2></div>
  <div class="grid-3">
    <div class="card"><div class="num">1</div><h3>Deep specialism</h3><p>Each division only recruits in its own sector, so we know the roles, the rates and the compliance inside out.</p></div>
    <div class="card"><div class="num">2</div><h3>One accountable person</h3><p>You deal with the Head of Recruitment directly, from the first call to the first day and beyond.</p></div>
    <div class="card"><div class="num">3</div><h3>Modern sourcing</h3><p>We use data-driven search and direct, personal outreach to reach the strong people who never look at job boards.</p></div>
  </div>
</div></section>

${founderBlock('group')}

<section class="alt"><div class="wrap">
  <div class="section-head"><span class="eyebrow">Insights</span><h2>Latest from the group</h2></div>
  <div class="post-grid">${latest}</div>
  <p style="margin-top:28px"><a class="btn btn-ghost" href="blog/index.html">All insights →</a></p>
</div></section>

<section><div class="wrap">${ctaBand('group', rel)}</div></section>`;
  return page('group', { title: `${g.name} | Specialist Recruitment in Care, Construction & Finance`, description: `${g.name}: specialist recruitment across nursing and care, engineering and construction, and accounting and finance. ${g.tagline}`, rel, canonical: '' }, body);
}

function groupContact() {
  const g = cfg.sites.group;
  const body = `
<section class="hero" style="padding-bottom:40px"><div class="wrap">
  <span class="eyebrow">Contact</span><h1>Let's talk.</h1>
  <p class="lead">Book a call directly, send us a message, or go straight to the specialist division for your sector.</p>
  <div class="btn-row">${SECTORS.map((k) => `<a class="btn btn-ghost" href="${siteLink(k, 'index.html', '')}">${esc(cfg.sites[k].name)}</a>`).join('')}</div>
</div></section>
<section style="padding-top:20px"><div class="wrap grid-2" style="align-items:start">
  <div class="card">
    <h3>Send a message</h3>
    <form class="stack" action="${cfg.formEndpoint}" method="POST" data-ajax>
      ${hidden('group', 'contact')}
      <div class="row-2"><div class="field"><label>Name</label><input name="name" required></div><div class="field"><label>Email</label><input type="email" name="email" required></div></div>
      <div class="row-2"><div class="field"><label>I am</label><select name="audience"><option value="client">Hiring</option><option value="candidate">Looking for work</option><option value="other">Something else</option></select></div>
        <div class="field"><label>Sector</label><select name="sector">${SECTORS.map((k) => `<option value="${k}">${esc(cfg.sites[k].sector)}</option>`).join('')}<option value="other">Other</option></select></div></div>
      <div class="field"><label>Message</label><textarea name="message" rows="5" required></textarea></div>
      <p class="consent">By sending this you agree to our <a href="privacy.html">privacy policy</a>.</p>
      <button class="btn btn-primary" type="submit">Send</button>
    </form>
    <div class="form-ok">Thanks, we've got your message and will reply shortly.</div>
    <p style="margin-top:24px" class="muted"><a href="mailto:${g.email}">${g.email}</a> · <a href="tel:${g.phone.replace(/\s/g, '')}">${g.phone}</a></p>
  </div>
  <div class="card" style="padding:0;overflow:hidden">
    <div class="calendly-inline-widget" data-url="${cfg.calendly.group}?hide_gdpr_banner=1&utm_source=website&utm_medium=group&utm_content=contact-page" style="min-width:300px;height:720px"></div>
    <script src="https://assets.calendly.com/assets/external/widget.js" async></script>
  </div>
</div></section>`;
  return page('group', { title: `Contact | ${g.name}`, description: `Contact ${g.name} or book a call.`, rel: '', canonical: 'contact.html', active: 'contact.html' }, body);
}

function privacyPage(key) {
  const s = cfg.sites[key];
  const body = `<section><div class="wrap article prose">
  <h1>Privacy policy</h1>
  <p><em>Placeholder. Replace with a policy reviewed for UK GDPR before going live.</em></p>
  <p>${esc(s.name)} is a trading name of ${esc(cfg.company.legalName)} (company no. ${esc(cfg.company.regNo)}), ${esc(cfg.company.address)}. We are the data controller for personal information you give us.</p>
  <h2>What we collect</h2><p>Details you submit through our forms or booking tools (name, contact details, role, CV, availability), plus information you have made public on professional networks, used to contact you about relevant roles or services.</p>
  <h2>How we use it</h2><p>To match candidates with roles, to talk to employers about their hiring needs, and to send occasional relevant updates. You can opt out at any time.</p>
  <h2>Your rights</h2><p>You can ask to access, correct or delete your data, or object to processing, by emailing <a href="mailto:${s.email}">${s.email}</a>.</p>
</div></section>`;
  return page(key, { title: `Privacy | ${s.name}`, description: `Privacy policy for ${s.name}.`, rel: '', view: key === 'group' ? null : 'client', canonical: 'privacy.html' }, body);
}

function favicon(key) {
  const s = cfg.sites[key];
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="${s.accent}"/><text x="32" y="43" font-family="Arial,sans-serif" font-size="34" font-weight="800" fill="#fff" text-anchor="middle">${esc(s.name[0])}</text></svg>`;
}

function seoFiles(key, pages) {
  const base = cfg.sites[key].url.replace(/\/$/, '');
  const urls = pages.map((p) => `  <url><loc>${base}/${p === 'index.html' ? '' : p.replace(/index\.html$/, '')}</loc></url>`).join('\n');
  return {
    'sitemap.xml': `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`,
    'robots.txt': `User-agent: *\nAllow: /\nSitemap: ${base}/sitemap.xml\n`,
  };
}

// ── BUILD ────────────────────────────────────────────────────
fs.rmSync(DIST, { recursive: true, force: true });
const posts = Object.fromEntries(ALL.map((k) => [k, loadPosts(k)]));
const sectorPosts = SECTORS.flatMap((k) => posts[k]).sort((a, b) => b.date.localeCompare(a.date));

for (const key of ALL) {
  const out = path.join(DIST, key);
  const files = {};
  if (key === 'group') {
    files['index.html'] = groupHome(posts.group, sectorPosts);
    files['contact.html'] = groupContact();
    files['blog/index.html'] = blogIndex(key, posts.group, sectorPosts);
  } else {
    files['index.html'] = sectorHome(key, posts[key]);
    files['hire.html'] = hirePage(key);
    files['register.html'] = registerPage(key);
    files['blog/index.html'] = blogIndex(key, posts[key]);
  }
  for (const p of posts[key]) files[`blog/${p.slug}.html`] = blogPost(key, p, posts[key]);
  files['privacy.html'] = privacyPage(key);
  Object.assign(files, seoFiles(key, Object.keys(files).filter((f) => f.endsWith('.html'))));

  for (const [f, html] of Object.entries(files)) write(path.join(out, f), html);
  fs.mkdirSync(path.join(out, 'assets'), { recursive: true });
  fs.copyFileSync(path.join(ROOT, 'src', 'styles.css'), path.join(out, 'assets', 'styles.css'));
  fs.copyFileSync(path.join(ROOT, 'src', 'main.js'), path.join(out, 'assets', 'main.js'));
  write(path.join(out, 'assets', 'favicon.svg'), favicon(key));
  console.log(`✓ ${key.padEnd(8)} ${Object.keys(files).length} files → dist/${key}/`);
}
if (LOCAL) write(path.join(DIST, 'index.html'), `<!doctype html><meta charset="utf-8"><title>Sites</title><body style="font-family:sans-serif;padding:40px"><h1>Local preview</h1><ul>${ALL.map((k) => `<li><a href="${k}/index.html">${esc(cfg.sites[k].name)}</a></li>`).join('')}</ul>`);
console.log(LOCAL ? 'Built with local links. Open dist/index.html.' : 'Built with production links (config urls).');
