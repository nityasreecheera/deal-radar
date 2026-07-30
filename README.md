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

The digest is the product. It arrives in Slack, because a radar you have to
remember to open is a radar you check twice and then forget.

Three surfaces, one job each:

- **Digest (Slack)** — the daily habit. Push, not pull.
- **Web** — where you go when something looks worth a closer look, and where you
  triage.
- **Agent chat** — ad-hoc research and steering, where judgement is needed.

A chatbot cannot be the main surface: you cannot ask about a company you do not
know exists. That is the entire problem being solved.

## Scope

Starting with **healthcare AI and clinical** — trials, diagnostics, care
coordination, health data.

That choice is practical, not sentimental: *Health Care* is one of the SEC's own
Form D industry categories, so filings can be pre-filtered almost for free.
Most software sectors land in "Technology → Other" and would require enriching
every filing before knowing whether it is even relevant.

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
data/radar.sqlite        seen-index and candidates
config/thesis.yaml       fit criteria — the file edited after talking to investors
outputs/digests/*.md     what was sent, so a digest can be audited later
```

`thesis.yaml` is a plain readable file on purpose. The criteria deciding what you
see should be something you can open and argue with, not weights buried in a
prompt.

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

The pipeline runs end to end against live EDGAR. A real digest from a two-day
window:

```
Deal Radar · 2 new · Healthcare AI and clinical software · 2026-07-29

1. Qualified Health PBC · $25M · San Carlos, CA
   ✓ An enterprise AI platform for health systems is clinical software
     applying machine learning to healthcare workflows.

2. ImmuNovus, Inc. · $5M · Denton, NE
   ~ Digital twin technologies could be computational drug discovery software
     (in scope) or primarily therapeutic development (out of scope), but the
     evidence doesn't specify whether the platform or a molecule is the asset.

Skipped 7 filings — already seen or filtered out.
Judged 8 as not a fit.
```

108 tests, none of which touch the network.

### What real filings changed

Four things were wrong in the design above, and only real data showed it.

**The healthcare industry filter excluded healthcare software.** Filtering on the
SEC's Health Care groups looked free and correct. Ambience Healthcare, Viz.ai and
Nabla all filed under *Other Technology*. The Health Care groups turned out to
contain surgical robotics, neuromodulation hardware, a prescription discount
card, a caregiver service, cell-factor therapeutics, and a house in Wayzata,
Minnesota.

**A $39 offering exists.** Hence a floor.

**But rejecting filings with no disclosed amount was worse.** Form D permits
indefinite offerings, and that rule silently dropped three real companies in a
single ten-day window. Absence of an amount is not evidence of a nominal raise,
and for a radar a missed company is the one failure that cannot be tolerated.

**An `ElementTree` element with no children is falsey**, so `find_element(...) or
fallback` silently takes the fallback even on success. Present twice, passing on
the sample filing by luck.

### Still to do

- Deliver the digest to Slack on a schedule
- The web reading surface, and the read-only chat over saved research
- Chip-sector market map

**And the thing that decides whether ranking is real or decorative:** the thesis
is still a placeholder. Fit criteria live in `config/thesis.yaml`, currently a
reasonable guess. What belongs there is a real mandate — stage, geography, cheque
size, and what kills a company in thirty seconds. That comes from talking to
investors, not from writing more code.

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
