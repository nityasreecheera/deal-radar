# Deal Radar

Every weekday morning, a short email of companies that just filed to raise money,
that you've never seen before, filtered down to the ones worth your time.

Not a database and not a search tool. It's a filter that remembers.

**Live:** [radar.humpback-pleco.ts.net](https://radar.humpback-pleco.ts.net) — continue
as a guest to browse the judgements, write criteria of your own and see them judged,
or ask the analysis page for a chart.

## About this project

A working tool, not a demo. It runs on a schedule against live SEC filings and
emails its results every weekday.

**Stack:** Python (FastAPI, Pydantic, SQLite) for the pipeline and API, Next.js and
TypeScript for the site, cron on an Oracle Cloud VM, published through Tailscale
Funnel. Any OpenAI-compatible model does the judging (Claude Sonnet through
OpenRouter here, a cheaper model for visitors); Tavily does the web search.

What's worth a look if you're reading the code:

- **It never invents an answer.** A malformed model reply or a failed lookup is
  recorded as a problem and retried the next day. It is never turned into a
  verdict, and the company is not marked as seen.
- **The categories came from the data.** `unknown` exists separately from `maybe`
  because twelve of the first twenty maybes turned out to mean "couldn't find out."
- **Your judgement overrides the model's, and both are kept,** so how often you
  disagree with it is a number rather than a feeling.
- **Public to read, private to change.** Anyone can browse the judgements. A
  visitor's database connection reads through views that leave out private
  domains and the owner's own notes, so no endpoint can leak them by forgetting
  a filter. Writing, spending and the criteria stay behind sign-in.
- **Visitors can try it without touching the record.** A guest writes their own
  domain and sees it judged against companies already looked up. Their domains
  live in tables of their own, read back through the same views, so they appear in
  that visitor's dropdown and nowhere else — never in the owner's data.
- **Charts from plain English, numbers from the data.** "Cornelis Networks vs
  DriveNets" or "raises by month": the model only picks from a closed set of chart
  plans; every figure is computed in Python through the viewer's own connection.
- **Every Form D is kept,** not just the ones a domain searched for — over 23,000
  since June — so a new domain can be run against months of history on the spot.
- **Access without accounts.** Invite links and read-only API tokens are signed
  and expire on their own. Nothing is stored server-side.
- **Over 500 tests that run offline.**

[DEVELOPING.md](DEVELOPING.md) covers the architecture and, more usefully, the
things real filings forced me to change.

## What you actually get

One email each weekday morning, around 9am US Eastern. Usually four or five names. Each one has what the company
does in a sentence, how much they're raising, how much has already sold, who's on
the filing, and a link to the source so you can check any of it.

```
Deal Radar · 2 new · Healthcare AI and clinical software · 2026-08-07

✓ Convexity Scientific Inc. · $13M · Indianapolis, IN
  Virtual COPD and chronic respiratory care platform.
  0% sold when filed · 3 investors

✓ Synthesis Health Inc. · $25.5M · Calgary, AB
  Workflow and reporting software for physicians, cloud-based imaging.
  100% sold when filed — likely closed

Skipped 47 filings — already seen or filtered out.
Judged 9 as not a fit.
```

Two minutes. That's the product.

## The problem it solves

Three things, all of them boring, which is why nobody builds for them:

- **You've seen most of these companies already.** You just can't remember which.
  Every database scrolls you past the same names you rejected last year.
- **The reason you passed disappears immediately.** Six months later it raises at
  5× and nobody can say why you said no.
- **Every new name costs the same twenty minutes** of looking things up, and nine
  times out of ten the answer is no.

## What it's found

Since June 2026 it has archived over 23,000 Form D filings and judged around a
thousand companies across six domains. Five are public examples — AI infra, AI
tools, Energy, Fintech and Healthcare — and one is private.

The first run, against healthcare filings from 1 June to 11 August, is the one that
showed what the ratio feels like:

```
304 companies seen  ·  239 judged
fits 8   ·   maybe 1   ·   unknown 45   ·   no_fit 185
```

The eight, all found from raw filings before any of them were announced:

| Company | Raising | What they do |
|---|---|---|
| Proxima Bio | $91.5M | AI drug discovery, proximity-based therapeutics |
| Kairo Health Labs | undisclosed | Testing and validation for healthcare AI models |
| Synthesis Health | $25.5M | Physician workflow and cloud imaging |
| Convexity Scientific | $13M | Virtual COPD and respiratory care |
| MemryHealth | $3M | EHR for post-acute care |
| Pretura Health | $2.5M | Emergency department coordination |
| PeriOp Ortho | $1.6M | Orthopedic surgery care coordination |
| 1104Health | undisclosed | Oncologist collaboration and trial software |

The ratio is the point. 239 companies looked at, 8 worth reading about. You saw
eight.

## What it costs

A few dollars a month. SEC filings are free and public. The model that reads each
company costs a couple of dollars at this volume, web search a little more, and the
server about five. Catching up a backlog costs more: judging a thousand companies
across five domains is roughly $10 on a cheap model and $50 on a strong one.

It runs on a small cloud server on a schedule. Nothing has to be open and nothing
has to be running. The site sits at a fixed address, open for anyone to read, and
both it and the daily run come back on their own after a reboot.

## How it works

```
every weekday  →  pull new SEC filings
               →  drop everything already seen
               →  look up what each company actually does
               →  judge it against your thesis
               →  email what's left
```

A company files a **Form D** with the SEC when it raises money. It's public the day
it's submitted, often before any announcement. What the form doesn't say is what the
company *does*, so each one gets looked up on the web, and then a model reads that
and decides whether it fits.

Every company lands in one of four buckets:

| | Meaning | In your email |
|---|---|---|
| **fits** | clearly in scope | yes |
| **maybe** | we know what they do, whether it fits is arguable | yes |
| **unknown** | we never found out what they do | counted only |
| **no fit** | clearly out of scope | counted only |

There's a separate `unknown` because twelve out of the first twenty maybes actually
meant "couldn't find out." Those are a different job. A *maybe* is worth two minutes,
an *unknown* is worth a search.

## There's also a website

The email is the daily habit. The website is where you go when something's worth a
closer look.

It has your domains in a dropdown, date pickers, and filters. Rows you've read go
grey; unread ones keep a coloured edge, so your eye finds them without reading
anything. Open a row and you get the company's website, the officers and directors,
how much of the round has sold, when it was incorporated, and a chart of every raise
they've ever filed.

Every company has a **note box and your own verdict buttons**. If the filter gets
one wrong, overrule it — your call wins everywhere afterwards, in the list and the
filters. Write down *why* while it's fresh: that's the thing that vanishes, and no
model can reconstruct it, because it came from a conversation or a hunch rather than
the filing. The filter's answer is kept underneath yours, so how often you disagree
with it is measurable — and that's the honest test of whether the thesis is right.

Visitors get the same pages read-only, without the owner's verdicts and notes, plus
two things of their own: **their own criteria** — write a domain, and it's judged on
the spot against companies already looked up — and **charts on request** on the
analysis page.

There's a question box at the bottom, but it only answers from companies already
judged. It can't search or research anything new, and the page says so. That's on
purpose: you can't ask about a company you don't know exists, and that's the whole
problem.

## What it deliberately won't do

- **It won't score a company.** Each one gets two lists — what the filings show
  in its favour, and what they don't — with the figure behind every line. No
  total, because totalling needs weights, and any weighting of "raised before"
  against "ten investors" is invented rather than read off a filing. And no
  probability: that needs outcomes to calibrate against, and no company on record
  has been acquired, failed, or floated.
- **It won't guess.** If the model returns something malformed, the run records a
  problem and moves on. It never invents a verdict, and it never marks that company
  as seen, so tomorrow tries again.
- **It won't scrape anything it isn't allowed to.** People changing jobs is the
  single strongest early signal there is, and it's off the table because it means
  LinkedIn.

## Where it honestly stands

It runs end to end against live filings, on a schedule, and emails the result.
Over 500 tests that run offline.

**The criteria are examples.** The public domains are a reasonable guess at what a
fund in each area would want, and nothing more. Every number on this page was
measured against criteria no investor has looked at yet.

What belongs there is a real mandate. Stage, geography, cheque size, and above all
what rules a company out in the first thirty seconds. That comes from a conversation,
not from writing more code. It's one config file to change, and it's the change that
decides whether any of this is useful.

**It went quiet for seven weeks, and said so.** From 18 August to 10 October the
web-search and model accounts ran out of credit. The radar kept fetching every
morning and its digest said, correctly, "none could be examined — this is not a
quiet day." Nobody was reading it. The lesson is that a job that reports its own
failure honestly still needs someone watching; the archive meant the backlog
could be judged afterwards rather than lost.

Known rough edges: Slack delivery exists in the code but has never been run, and
each morning's digest is saved per day rather than per domain, so the saved file
holds only the last domain to run.

---

Technical detail — architecture, running it, the schema, and what the real data
forced me to change — is in **[DEVELOPING.md](DEVELOPING.md)**.
