# Deal Radar

A daily digest of companies that just became visible, that you have never seen
before, ranked against what you actually invest in.

Not a search tool. Not a database. A filter with a memory.

## The problem

An investment analyst's day is not short of information — it is drowning in it.
The recurring pain is not "I cannot find companies," it is:

1. **Recall, not search.** *"I saw a company like this eight months ago — who was
   it?"* Notes live in email, in a CRM nobody updates, in someone's head.
2. **Screening is repetitive but needs judgement.** Every inbound needs the same
   lookups: what do they do, what stage, where, who's the team, is this in our
   box. Twenty to forty minutes, and nine times in ten the answer is no.
3. **Signal detection.** Knowing who is *about* to be interesting — the actual
   craft, and the hardest part to systematise.
4. **The mandate is implicit.** Everyone "knows" what the fund invests in, but it
   is not written down anywhere applicable, so screening quality varies by who
   happens to be doing it.
5. **Reasoning evaporates.** Passing on a company is the most information-dense
   event in the job. Six months later it raises at 5× and nobody remembers why
   the answer was no.
6. **Relationship state.** *Have we spoken to them? Who? When? What did we say?*

Problems 1, 5 and 6 are the least glamorous and the most genuinely unsolved.
This project starts there.

## Why not just use Crunchbase

Crunchbase has more data than this project will ever have, and that is not the
axis worth competing on. What it cannot do:

- **It does not remember what you have already seen.** Every search scrolls past
  the same companies you looked at and rejected last year. You redo that work
  every time.
- **It does not know what you care about.** You re-describe it in filters, every
  session.

| Crunchbase | Deal Radar |
|---|---|
| You go to it | It comes to you |
| Search, scroll, filter | A short list, already filtered |
| You recognise stale names yourself | Stale names are never shown |
| 30–45 minutes | 2 minutes |

Crunchbase is a supermarket: everything is there, and you do the shopping. This
is someone who knows what is in your fridge.

The two are not really competitors. Crunchbase could be a *source* for this. The
product is the filter and the memory sitting on top, whichever database is
underneath.

### On speed — the honest version

**This does not get data faster than Crunchbase.** Crunchbase ingests the same
public filings automatically, within a day or two, and anything a company
announces publicly reaches them the same day. Any claim to earlier data would
not survive a follow-up question.

One narrow exception: small unannounced raises — a $2M seed with no press
release — are curated slowly or thinly everywhere, so there we can be genuinely
days ahead. That is a real but niche claim, not a headline.

The defensible speed claim is different. Data arriving is not the bottleneck;
*you finding out* is. Data can sit in Crunchbase for a week while you remain
unaware, because you have not run the right search yet. Here it arrives already
filtered, so you know days sooner even when the underlying data landed at the
same moment.

**Not faster data. Faster to the person who needs it.**

## Sources, organised by latency

Which tier a source sits in matters more than which source it is.

**Too late to be differentiated** — press, newsletters, podcasts, most of
Twitter. By the time something is here, every fund has seen it. Useful for
calibrating on narrative, not for discovery.

**Simultaneous** — Y Combinator's directory and Demo Day, Techstars batches,
Product Hunt. Pre-vetted and good, but everyone sees them the same day, so the
only edge is speed of response.

**Low latency, high noise — where the edge is:**

- **People moves.** A strong operator leaving a good company is a company about
  to exist. Months earlier than anything else. Also the hardest to obtain
  legitimately, since it means LinkedIn, whose terms prohibit scraping.
- **Hiring.** A first enterprise sales role means moving upmarket. A first ten
  engineers means they raised.
- **Regulatory filings.** SEC Form D is filed when a company raises, sometimes
  before any announcement. Public, structured, free.
- **Launch HN / Show HN.** A company's earliest public moment, in the founder's
  own words.
- **Developer traction** — GitHub stars, package download curves — for developer
  tools specifically.
- **Papers to spinouts.** For AI and deep tech, authors and lab affiliations
  predict companies by 12–18 months.

This tier needs tooling precisely *because* it is noisy. Low-latency signals are
only valuable if something filters them, and filtering by hand daily is too
expensive to sustain.

**Paid, and mostly the money layer** — PitchBook, Crunchbase. Valuations, round
history, comparables. Hard to substitute, easy to defer.

## What it does

```
daily  → pull a low-latency source
       → drop anything already seen
       → judge fit against the thesis, write one line of why
       → digest: a handful of genuinely new names, ranked
       → triage into the pipeline in two minutes
```

The digest is the product. It arrives by email, because a radar you have to
remember to open is a radar you check twice and then forget. Email rather than
Slack because it needs a password and nothing else — no workspace, no app, no
admin approval.

Three surfaces, one job each:

- **Digest (email)** — the daily habit. Push, not pull.
- **Web** — where you go when something looks worth a closer look, and where you
  triage.
- **Agent chat** — ad-hoc research and steering, where judgement is needed.

A chatbot cannot be the main surface: you cannot ask about a company you do not
know exists. That is the entire problem being solved.

### Four verdicts

Each company gets one of four, and the fourth exists because of real data rather
than tidiness.

| Verdict | Meaning | In the digest? |
|---|---|---|
| `fits` | clearly within the thesis | yes |
| `maybe` | the business is known, the fit is arguable | yes |
| `unknown` | the evidence never said what it does | counted only |
| `no_fit` | clearly outside it | counted only |

`maybe` and `unknown` began as one bucket. In practice twelve of twenty maybes
meant "we could not find out" — a placeholder site, boilerplate, nothing at all.
Reading those as judgements filled half the digest with shrugs, which is the
fastest way to make a daily read stop being read. An analyst treats them
differently: a maybe is worth a look, an unknown is worth a search.

Alongside the verdict, the judge writes a **one-line summary of the business**,
kept separate from its reason. The reason explains the decision; the summary
describes the company. Conflating them meant the only available description was
a raw search snippet, which is usually boilerplate.

## Scope

Starting with **healthcare AI and clinical** — trials, diagnostics, care
coordination, health data.

An early assumption here was wrong and worth recording. *Health Care* is one of
the SEC's own Form D industry categories, which looked like a free pre-filter.
It is not: healthcare **software** files under *Technology*. Verified against real
filings — Ambience Healthcare ($70M), Viz.ai and Nabla all used "Other
Technology", and the Health Care groups turned out to hold surgical robotics,
neuromodulation devices, therapeutics, a prescription discount card and a
residential property in Wayzata, Minnesota.

So the search covers Technology as well, which costs volume — roughly 350 extra
filings a month against 150 healthcare ones, all of them enriched and judged.
There is no cheaper shortcut: names like "Abridge" and "Nabla" carry no signal,
so anything relevant has to be looked up to be found.

**Semiconductors** are tracked differently. Designing silicon costs tens of
millions, so only a handful of companies start per year worldwide — a daily
radar would be empty most days, and chip startups file under "Technology"
alongside every SaaS company, so the cheap pre-filter does not apply. For chips
the useful artefact is a **market map** of who exists now, refreshed
occasionally, plus chip-specific signals later: CHIPS Act and DARPA awards
(public and structured), academic spinouts, and hiring for physical-design and
verification roles.

Different sectors want different products. Long tail of new companies wants a
radar. Short list of known players wants a map.

## Architecture

```
CRON  (daily, on the VM — nothing needs to be running)
  │
  1. FETCH      SEC EDGAR daily index → Form D filings
  │             stdlib XML parse, no model involved
  │
  2. FILTER     keep industryGroup == "Health Care"
  │             free — it is a field in the filing itself
  │
  3. DEDUPE     SQLite seen-index, by canonical domain
  │             then normalised name.  ← this is the product
  │             (only new companies pass through)
  │
  4. ENRICH     what does this company actually do?
  │             a filing barely says, so look it up
  │
  5. JUDGE      fit against the thesis, plus one line of why
  │             ← the only step where a model has an opinion
  │
  6. RECORD     write to the seen-index and the candidate store
  │
  7. DIGEST     render, then push to Slack
  │
  └──────────────────────────────────────────────────
        the same store is read by:
        · the web UI — browse, triage
        · the chat endpoint — read-only, no tools
```

Steps 1–3 and 6 are ordinary deterministic software, testable offline with no
network. Step 5 is the only place a model forms a judgement, and its output is
schema-validated before anything is written.

**Judgement from the model, mechanics from software, validation as the guardrail
between them.**

## Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11 | this is I/O and parsing |
| Seen-index | SQLite (stdlib) | exact lookups, thousands of rows, hit per filing |
| Schemas | Pydantic | the validation boundary |
| HTTP | httpx | — |
| Filing parse | `xml.etree` (stdlib) | Form D is small structured XML |
| Enrichment | Tavily | web lookup for what a company does |
| Fit judgement | Claude API, structured output | batch scoring, no agent loop needed |
| Deep research | Hermes agent + skill | interactive and steerable, has tools |
| Digest delivery | `hermes send -t slack` | already built and credentialed |
| API | FastAPI | OpenAPI schema generated from the Pydantic models |
| Web | Next.js + Tailwind | frontend types generated from that schema |
| Chat | FastAPI + Claude API, no tools | capability-restricted by construction |
| Schedule | systemd timer | survives reboots, needs nothing else running |

### Three decisions worth recording

**Claude API for scoring, Hermes for research.** A deliberate split. Scoring
thirty filings a day is a short structured judgement per item; an agent loop with
tool access would take far longer per filing and add nothing. Hermes stays for
interactive work, where steering and follow-up questions are the point.

**SQLite, not JSON files.** The sibling project stores JSON on disk, which is
right for dozens of profiles. The seen-index is a lookup workload that grows into
the thousands and is queried on every filing. SQLite is in the standard library,
so adopting it costs nothing.

**Copy the normalisers, do not couple the repositories.** `normalize_domain` and
`normalize_company_name` from the sibling project are about forty lines and
exactly what deduplication needs here. Copied with a note on their origin, rather
than making one early-stage project depend on another while both are still
changing shape.

## Where things run

- **VM** — cron, ingestion, SQLite, API, web. It is the always-on machine.
- **Laptop** — development and git.
- **Slack** — where the digest arrives.
- **Nothing public** beyond what is deliberately tunnelled.

## Storage

```
data/radar.sqlite        seen-index, and every judgement with its reasoning
config/*.yaml            one file per domain — the files edited after talking to investors
outputs/digests/*.md     what was sent, so a digest can be audited later
outputs/logs/radar.log   what each scheduled run did
web/.env.local           credentials for publishing (ignored)
```

Two tables. `seen_company` answers "have I encountered this company?" and needs to
do nothing else. `candidate` answers "what did I decide, and why?" — which is the
question actually asked six months later, and the one that used to be discarded
the moment a digest was rendered. Keyed on accession rather than company, because
a company can file more than once and each filing is a separate judgement made on
separate evidence.

`thesis.yaml` is a plain readable file on purpose. The criteria deciding what you
see should be something you can open and argue with, not weights buried in a
prompt.

## Running it

```bash
python3.11 -m venv .venv          # 3.11 or newer: `str | None` in annotations
.venv/bin/pip install -r requirements.txt

cp .env.example .env              # then fill in the keys
```

Keys and what each is for are documented in [.env.example](.env.example). Two are
required: `TAVILY_API_KEY` for finding out what a company does, and
`OPENROUTER_API_KEY` for judging fit. Email delivery is optional and needs
`SMTP_USER` and `SMTP_PASSWORD` — for Gmail that must be an App Password, not the
account password, which is the one mistake everybody makes.

Port 25 is blocked outbound on Oracle Cloud; 587 and 465 are open, so Gmail over
STARTTLS works.

### The radar

```bash
# a run over the default window (3 days, so a Monday catches Friday)
.venv/bin/python -m src.cli run

# any window, and email it
.venv/bin/python -m src.cli run --start 2026-06-01 --end 2026-06-15 --send

# rehearse without consuming the novelty of everything it looks at
.venv/bin/python -m src.cli run --dry-run

# what has been decided, and why
.venv/bin/python -m src.cli candidates --verdict fits
.venv/bin/python -m src.cli candidates --company Genomenon
.venv/bin/python -m src.cli status
```

Any date range is safe to re-run. Deduplication is exact, so overlapping windows
cost nothing but a "skipped" line.

### On a schedule

```
MAILTO=""
RADAR_SEND=1
0 13 * * 1-5 /home/opc/deal-radar/scripts/daily.sh
```

Weekdays at 13:00 UTC, weekdays only because EDGAR does not publish at weekends.
Delivery is opt-in through `RADAR_SEND` so a missing mail credential cannot fail a
run whose real work — extending the seen-index — succeeded.

### The web interface

```bash
./scripts/web.sh                  # API on 8100, site on 3100
```

Then from your own machine:

```bash
ssh -L 3100:localhost:3100 oci
```

Ports 3100 and 8100 rather than 3000 and 8000, so this does not collide with
anything else on the same host.

The page has a domain dropdown, date pickers bounded to the filings actually on
record, verdict filters, an unread-only toggle, and a question box. Read rows grey
out and lose their accent; unread rows keep it. The contrast is the point — the
eye should find the unread ones without reading a word.

Expanding a row shows the business summary, the website, officers and directors
with their roles and locations, funding raised against sold, investor count,
incorporation year, entity type, jurisdiction, and a link to the filing itself so
any claim can be checked at source.

### Publishing it

```bash
printf 'SHARE_USER=review\nSHARE_PASSWORD=...\n' > web/.env.local
./scripts/share.sh
```

Serves the production build through a Cloudflare quick tunnel. No security-list
change and no open port — cloudflared dials outward.

The password is not optional and the script refuses to publish without one:
`/api/chat` spends money per request and `/api/viewed` writes, so an ungated URL
is someone else's ability to run up a bill. `share.sh` verifies the site answers
401 before opening the tunnel rather than assuming the gate works. The chat is
also capped at sixty questions an hour, which turns a runaway into a refusal.

The URL is temporary and different every run.

## Layout

| Module | Does |
|---|---|
| [src/edgar.py](src/edgar.py) | EDGAR search and Form D parsing; the fetcher is injectable so tests stay offline |
| [src/normalize.py](src/normalize.py) | company identity — canonical domain, normalised name |
| [src/seen.py](src/seen.py) | the seen-index, the schema, and in-place migration |
| [src/thesis.py](src/thesis.py) | what counts as interesting, and the free filters applied first |
| [src/enrich.py](src/enrich.py) | what a company actually does, since a filing never says |
| [src/judge.py](src/judge.py) | the one step where a model forms an opinion |
| [src/candidates.py](src/candidates.py) | every judgement and its reasoning, queryable |
| [src/pipeline.py](src/pipeline.py) | the run, and the ordering rules that make it safe |
| [src/digest.py](src/digest.py) | the message that gets read |
| [src/delivery.py](src/delivery.py) | email over SMTP, or Slack through the agent |
| [src/chat.py](src/chat.py) | answering questions from stored judgements, with no tools |
| [src/api.py](src/api.py) | HTTP for the interface; read-mostly |
| [src/cli.py](src/cli.py) | the command surface |
| [web/](web/) | the reading interface — Next.js, types generated from the API schema |

Frontend types come from the OpenAPI schema, so `src/models.py` is the single
source of truth and there is no second definition to drift:

```bash
cd web && npm run gen:types      # needs the API running
```

That has caught real bugs. A Pydantic field with a `default_factory` is not
"required" in the schema, so every list arrives typed as possibly-undefined and
the compiler rejects unguarded use. And a `@property` on a Pydantic model is
**not serialised**, so `is_unread` and `filing_url` never reach the browser and
are derived client-side instead.

## Scripts

| Script | For |
|---|---|
| `scripts/daily.sh` | one run, for cron; logs the digest and its own commentary |
| `scripts/web.sh` | API and site locally, in tmux |
| `scripts/share.sh` | production build behind a password, on a public URL |
| `scripts/diagnose.py` | every company with its evidence and the reason it was judged |
| `scripts/backfill_detail.py` | re-fetch filing detail for rows saved before it was stored |
| `scripts/rejudge.py` | re-judge stored rows after the prompt or verdict set changes |

`diagnose.py` earns its place: a radar that rejects everything is
indistinguishable from a broken one unless the reasoning is visible. The first
live run rejected all six companies — correctly, as it turned out, but that was
only checkable by reading the reasons.

`rejudge.py` matters whenever the prompt changes, because stored rows keep
verdicts reached under the old rules. It re-enriches as well as re-judging: a
verdict reached on absent evidence deserves another look at the evidence rather
than a relabelling.

## Schema changes

The database is migrated in place on every connect. `CREATE TABLE IF NOT EXISTS`
does nothing to a table that already exists, so new columns are added explicitly
in `MIGRATIONS` or a deployed database silently lacks them.

Order matters and is easy to get wrong: **tables, then columns, then indexes**. An
index on a column migration has not yet added cannot be created, so a single
schema script fails on any database older than its newest column. The migration
tests build a deliberately old-shaped database for exactly this reason — a fresh
one would pass happily and hide the bug.

## Deliberate non-goals

- **No LLM calls in the data layer.** Fetching, deduplication, and validation are
  ordinary software and stay deterministic and testable. Judgement — is this a
  company, does it fit — belongs to the agent.
- **No search box.** Search finds what has already been written about, which is
  the latest possible tier. A search box would be convenient and produce worse
  sourcing.
- **No scraping of sources whose terms forbid it.** LinkedIn is the highest-value
  signal and is off the table for that reason.
- **No investment-attractiveness score.** Software can measure whether research
  is well-evidenced. Whether a company is a good investment is the analyst's
  judgement, and a number computed in Python would only launder an opinion.

## Status

Runs end to end against live EDGAR, on a schedule, delivering by email, with a
web interface behind a password. **207 tests, none of which touch the network.**

Over 1 June to 17 July 2026 — 202 companies seen:

```
fits 5   ·   maybe 1   ·   unknown 15   ·   no_fit 116
```

The five fits, all found from raw filings:

| Company | Raise | What it does |
|---|---|---|
| Proxima Bio | $91.5M | AI drug discovery, proximity-based therapeutics |
| MemryHealth | $3M | EHR for post-acute care, documentation automation |
| Pretura Health | $2.5M | emergency department workflow coordination |
| PeriOp Ortho | $1.6M | orthopedic surgery care coordination |
| 1104Health | undisclosed | oncologist collaboration and trial software |

### What real data changed

Six things were wrong in the design above, and only real filings showed it.

**The healthcare industry filter excluded healthcare software.** Covered under
Scope. The single most consequential error here — the free pre-filter was
filtering out the target.

**A $39 offering exists.** Hence a floor.

**But rejecting filings with no disclosed amount was worse.** Form D permits
indefinite offerings, and that rule silently dropped three real companies in one
ten-day window. Absence of an amount is not evidence of a nominal raise, and for
a radar a missed company is the one failure that cannot be tolerated.

**Half the maybes were not maybes.** Twelve of twenty meant "we could not find
out". Hence the fourth verdict.

**Enrichment was reading legal boilerplate.** Search returns whichever page
matched a company name, which is very often the privacy policy or the leadership
team — pages on the right domain that describe nothing. Preferring the shallowest
non-boilerplate URL turned unresolvable shrugs into decisions: PreventiveMD moved
from its terms page to its homepage, revealing a GLP-1 telehealth service, which
is a clean rejection rather than a maybe.

**An `ElementTree` element with no children is falsey**, so `find_element(...) or
fallback` silently takes the fallback even on success, and `if offering` treats an
empty `<offeringData/>` as missing. Present twice, passing on the sample filing by
luck.

### Still to do

- Chip-sector market map
- Slack as an alternative to email — wired, not credentialed
- Automated monitoring beyond a fixed daily window

**And the thing that decides whether any of this is real:** the thesis is still a
placeholder. Fit criteria live in `config/thesis.yaml`, currently a reasonable
guess. What belongs there is a real mandate — stage, geography, cheque size, and
what kills a company in thirty seconds. That comes from talking to investors, not
from writing more code. Every verdict above was measured against criteria nobody
in the industry has reviewed.

Building on [investment-research-copilot](https://github.com/nityasreecheera/investment-research-copilot),
which already contributes the parts that matter here: deduplication by canonical
domain then normalised name, a record of everything already researched, pipeline
state with an enforced reason on every pass, and schema validation as a guardrail
on generated content.

**Next:** SEC Form D ingestion, filtered to Health Care, deduplicated against
everything already seen.

**Open, and the thing that decides whether ranking is real or decorative:** the
thesis. Fit criteria live in a config file, currently a placeholder. What belongs
there is a real mandate — stage, geography, cheque size, and what kills a company
in thirty seconds. That comes from talking to investors, not from guessing.
