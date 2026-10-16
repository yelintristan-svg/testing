// ─────────────────────────────────────────────────────────────
//  SITE CONFIG — edit this file, then run `node build.js`
//  Everything a placeholder is marked with  ← SWAP
// ─────────────────────────────────────────────────────────────

module.exports = {
  // One Calendly link per site (can all be the same link to start).
  // Use your own event, e.g. https://calendly.com/tristan-meridian/intro-call
  calendly: {
    group:   'https://calendly.com/YOUR-HANDLE/intro-call',        // ← SWAP
    care:    'https://calendly.com/YOUR-HANDLE/care-intro',        // ← SWAP
    build:   'https://calendly.com/YOUR-HANDLE/build-intro',       // ← SWAP
    finance: 'https://calendly.com/YOUR-HANDLE/finance-intro',     // ← SWAP
  },

  // Where every form POSTs. Formspree / Basin / Tally work out of the box;
  // later point this at the CRM's intake endpoint. Each submission carries
  // hidden fields `site` and `form` so the CRM knows where it came from.
  formEndpoint: 'https://formspree.io/f/YOUR_FORM_ID',              // ← SWAP

  owner: {
    name: 'Tristan',                                                // ← SWAP (full name)
    title: 'Head of Recruitment',
    linkedin: 'https://www.linkedin.com/in/YOUR-PROFILE',           // ← SWAP
  },

  social: {
    linkedin:  'https://www.linkedin.com/company/YOUR-COMPANY',     // ← SWAP
    twitter:   'https://x.com/YOUR-HANDLE',                         // ← SWAP
    instagram: 'https://instagram.com/YOUR-HANDLE',                 // ← SWAP
  },

  company: {
    legalName: 'Meridian Talent Group Ltd',                         // ← SWAP
    regNo: '00000000',                                              // ← SWAP
    address: 'London, United Kingdom',                              // ← SWAP
  },

  sites: {
    group: {
      name: 'Meridian Talent Group',                                // ← SWAP
      short: 'Meridian',
      url: 'https://meridiantalent.co.uk',                          // ← SWAP
      email: 'hello@meridiantalent.co.uk',                          // ← SWAP
      phone: '+44 20 0000 0000',                                    // ← SWAP
      accent: '#3b5bdb',
      accentDark: '#1e2f7a',
      tagline: 'Specialist recruitment for the people who keep the country running.',
    },
    care: {
      name: 'Meridian Care',                                        // ← SWAP
      short: 'Care',
      sector: 'Nursing, Medical & Care',
      url: 'https://meridiancare.co.uk',                            // ← SWAP
      email: 'care@meridiantalent.co.uk',                           // ← SWAP
      phone: '+44 20 0000 0001',                                    // ← SWAP
      accent: '#0f9d8a',
      accentDark: '#08564c',
      model: 'Temp & locum first, permanent alongside',
      modelWhy: 'Care and clinical services run on shift cover. Most demand is for reliable agency and locum staff at short notice, so that is where we lead, with permanent hires for wards, homes and practices that want to stop relying on agency.',
      client: {
        eyebrow: 'For care homes, clinics & NHS trusts',
        h1: 'Safe, compliant shift cover. Filled fast.',
        sub: 'Registered nurses, HCAs, support workers and clinicians, pre-vetted with DBS, right to work and references checked before they ever reach your door.',
        cta: 'Book a staffing call',
        points: [
          ['Compliance done first', 'Enhanced DBS, NMC/HCPC PIN checks, mandatory training and references verified up front.'],
          ['Short-notice cover', 'Tell us the shift, grade and site. We match from people already cleared and available.'],
          ['Temp-to-perm option', 'Like someone on shift? Move them onto your payroll on clear, fair terms.'],
        ],
        roles: ['Registered Nurses (RGN/RMN)', 'Healthcare Assistants', 'Senior Carers', 'Support Workers', 'Care Home Managers', 'Theatre & ODP Staff', 'Allied Health Professionals', 'Domiciliary Carers'],
      },
      candidate: {
        eyebrow: 'For nurses, carers & clinicians',
        h1: 'Pick your shifts. Get paid weekly.',
        sub: 'Flexible agency work, locum placements and permanent roles across care homes, hospitals and community services, with one person who actually picks up the phone.',
        cta: 'Register in 2 minutes',
        points: [
          ['You choose when', 'Days, nights, weekends or block bookings. Work around your life, not the rota.'],
          ['Weekly pay', 'Competitive rates, paid on time every week, with holiday pay accrued.'],
          ['Compliance help', 'We help you get your DBS, training and documents sorted so you can start sooner.'],
        ],
      },
    },
    build: {
      name: 'Meridian Build',                                       // ← SWAP
      short: 'Build',
      sector: 'Engineering, Construction & Technical Trades',
      url: 'https://meridianbuild.co.uk',                           // ← SWAP
      email: 'build@meridiantalent.co.uk',                          // ← SWAP
      phone: '+44 20 0000 0002',                                    // ← SWAP
      accent: '#e8590c',
      accentDark: '#8a3104',
      model: 'Contract & temp for site, permanent for engineers',
      modelWhy: 'Construction is project-based: trades, labour and site teams are hired for the length of a job, so we lead with contract and temp. Engineers, project managers and estimators are long-term hires, so those we place permanently.',
      client: {
        eyebrow: 'For contractors, developers & engineering firms',
        h1: 'Tickets checked. On site Monday.',
        sub: 'Skilled trades, site managers and engineers matched to your programme, with CSCS, SSSTS/SMSTS and trade cards verified before day one.',
        cta: 'Book a resourcing call',
        points: [
          ['Cards and tickets verified', 'CSCS, CPCS, SSSTS/SMSTS, 18th Edition and IPAF checked before anyone is sent.'],
          ['Scale with the programme', 'Ramp crews up and down by phase without carrying the payroll between jobs.'],
          ['Permanent engineering hires', 'Project managers, QSs, estimators and engineers placed on a clear fee.'],
        ],
        roles: ['Electricians', 'Plumbers & Gas Engineers', 'Site Managers', 'Quantity Surveyors', 'Project Managers', 'Civil & Structural Engineers', 'Maintenance Technicians', 'Groundworkers & Labourers'],
      },
      candidate: {
        eyebrow: 'For trades, site teams & engineers',
        h1: 'Better rates. Steady work. No messing about.',
        sub: 'Contract, temp and permanent roles with contractors who pay on time, near where you live, with a recruiter who tells you the real rate up front.',
        cta: 'Register for work',
        points: [
          ['Rates up front', 'Day rate, hours, location and duration before you say yes. No surprises on site.'],
          ['Back-to-back work', 'We line up the next job before this one ends so you are not sat waiting.'],
          ['Career moves', 'Want to step up to supervisor or go perm? We will help you plan it.'],
        ],
      },
    },
    finance: {
      name: 'Meridian Finance',                                     // ← SWAP
      short: 'Finance',
      sector: 'Accounting & Finance',
      url: 'https://meridianfinance.co.uk',                         // ← SWAP
      email: 'finance@meridiantalent.co.uk',                        // ← SWAP
      phone: '+44 20 0000 0003',                                    // ← SWAP
      accent: '#2f6f4f',
      accentDark: '#173a29',
      model: 'Permanent first, interim when you need it',
      modelWhy: 'Finance teams hire for the long term, so most of our work is permanent placements. When there is a month-end crunch, an audit, a system migration or a leave gap, we supply interim and contract accountants.',
      client: {
        eyebrow: 'For finance leaders & business owners',
        h1: 'Accountants who fit the team and stay.',
        sub: 'Qualified and part-qualified finance professionals, from AP clerks to Financial Controllers, shortlisted on technical ability and how they will actually work with you.',
        cta: 'Book a hiring call',
        points: [
          ['Shortlists, not CV piles', 'Three to five properly screened candidates, each with a short note on why they fit.'],
          ['Interim cover', 'Month-end, audit, systems projects or parental leave, covered by experienced contractors.'],
          ['Fair, simple fees', 'Clear permanent fee with a rebate period. No retainer needed to get started.'],
        ],
        roles: ['Financial Controllers', 'Management Accountants', 'Finance Business Partners', 'Payroll Specialists', 'Credit Controllers', 'AP / AR Clerks', 'Interim CFOs & FDs', 'Assistant Accountants'],
      },
      candidate: {
        eyebrow: 'For accountants & finance professionals',
        h1: 'Your next finance role, without the noise.',
        sub: 'Permanent and interim roles that match your qualifications, salary expectations and the way you want to work, hybrid included.',
        cta: 'Register confidentially',
        points: [
          ['Confidential by default', 'Your CV never goes anywhere without your say-so.'],
          ['Study support matters', 'We prioritise employers who back ACCA, CIMA and ACA study.'],
          ['Honest salary advice', 'Real market numbers so you can negotiate with confidence.'],
        ],
      },
    },
  },
};
