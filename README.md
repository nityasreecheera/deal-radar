# Deal Radar

Every weekday morning this emails me a short list of companies that just showed up
in SEC filings, that I haven't seen before, filtered down to the ones worth a look.

It's not a search tool and it's not another database. It's a filter that remembers
what you've already seen.

## Why I built it

Analysts aren't short of information — they're drowning in it. The annoying parts
are the boring ones:

- *"I saw a company like this eight months ago, who was it?"* The notes are in
  email, or a CRM nobody updates, or somebody's head.
- Deciding to pass on a company is the most useful thing you learn all week, and
  the reason vanishes almost immediately. Six months later it raises at 5× and
  nobody remembers why you said no.
- Every new company needs the same twenty minutes of looking things up, and nine
  times out of ten the answer is no.

Nobody builds for these because they're dull. So that's where I started.

## Why not just use Crunchbase

Crunchbase has far more data than this ever will, and that's not worth competing
on. But there are two things it can't do:

- **It doesn't remember what you've already seen.** Every search scrolls past the
  same companies you looked at and rejected last year.
- **It doesn't know what you care about.** You have to describe that again, in
  filters, every time.

| Crunchbase | Deal Radar |
|---|---|
| You go to it | It comes to you |
| Search, scroll, filter | A short list, already filtered |
| You spot the stale names yourself | Stale names never show up |
| 30–45 minutes | 2 minutes |

Crunchbase is a supermarket — everything's there and you do the shopping. This is
more like someone who knows what's in your fridge.

They're not really competitors. Crunchbase could be a source *for* this. The useful
bit is the filtering and the memory on top, whatever database is underneath.

### On speed, honestly

**This doesn't get data faster than Crunchbase.** They pull the same public filings
automatically within a day or two, and anything a company announces publicly hits
them the same day. If I claimed to be earlier, that wouldn't survive one
follow-up question.

There's a narrow exception. Small unannounced raises — a $2M seed with no press
release — get curated slowly everywhere, so on those this can genuinely be days
ahead. That's real, but it's niche.

The claim that does hold is a different one. Data arriving isn't the bottleneck —
*you finding out* is. Something can sit in Crunchbase for a week while you have no
idea, because you haven't run the right search. Here it just turns up, already
filtered. So you find out sooner even when the data landed at exactly the same
moment.

## Where the data comes from

Which *tier* a source sits in matters more than which source it is.

**Too late to be useful** — press, newsletters, podcasts, most of Twitter. By the
time something's here every fund has seen it. Fine for understanding the narrative,
no use for finding companies first.

**Everyone at once** — YC's directory and Demo Day, Techstars batches, Product
Hunt. Genuinely good and already vetted, but everyone sees them the same day, so
the only edge left is how fast you reply.

**Early and noisy, which is where the edge actually is:**

- **People moving jobs.** A good operator leaving a good company is a company about
  to exist. That's months earlier than anything else. It's also the hardest to get
  honestly, because it means LinkedIn and their terms don't allow scraping.
- **Hiring.** A first enterprise sales hire means they're moving upmarket. A first
  ten engineers means they raised.
- **Regulatory filings.** US companies file an SEC Form D when they raise, sometimes
  before announcing anything. Public, structured, free. **This is what the radar
  uses right now.**
- **Launch HN and Show HN.** The earliest a company describes itself publicly, in
  the founder's own words.
- **Developer traction** — GitHub stars, package downloads — for dev tools.
- **Research papers.** In AI, authors and lab affiliations predict companies by a
  year or more.

This tier needs software precisely *because* it's noisy. Early signals are only
worth having if something filters them, and doing that by hand every day isn't
sustainable.

**Paid, and mostly about money** — PitchBook, Crunchbase. Valuations, round
history, comparables. Hard to replace, easy to put off.

## How it works

```
every weekday  → pull new SEC filings
               → drop anything already seen
               → look up what each company actually does
               → judge it against the thesis
               → email a short list
```

The email is the point. A radar you have to remember to open is one you check twice
and then forget about.

Email rather than Slack because it only needs a password. No workspace, no app to
create, nobody's approval.

There are two places to look and each does one job:

- **The email** — the daily habit. It comes to you.
- **The website** — where you go when something looks worth a closer look, where
  you mark things read, and where you can ask questions about what's already been
  judged.

Deliberately not a chatbot, or at least not primarily. You can't ask about a
company you don't know exists, and that's the entire problem. The question box on
the website is for recall — *which ones did we pass on, and why* — not for finding
anything new.

### The four verdicts

Every company gets one of four. There's a fourth because of what the real data
looked like, not because four is neater than three.

| Verdict | What it means | In the email? |
|---|---|---|
| `fits` | clearly in scope | yes |
| `maybe` | we know what they do, whether it fits is arguable | yes |
| `unknown` | we never found out what they do | counted only |
| `no_fit` | clearly out of scope | counted only |

`maybe` and `unknown` used to be the same bucket. Then twelve of twenty maybes
turned out to mean "couldn't find out" — placeholder website, boilerplate, nothing
at all. That filled half the email with shrugs, which is the fastest way to stop
someone reading it. And you'd treat them differently anyway: a maybe is worth a
look, an unknown is worth a search.

The judge also writes **one line on what the company does**, separate from why it
gave that verdict. The reason explains the decision, the summary describes the
business. When those were one field, the only description available was a raw
search snippet, which is usually legal boilerplate.

## What it looks for

Right now: **healthcare AI and clinical software** — trials, diagnostics, care
coordination, health data.

I got something wrong here early on and it's worth writing down. *Health Care* is
one of the SEC's own industry categories on Form D, so filtering on it looked like
a free way to narrow things. It isn't, because healthcare **software** files under
*Technology* instead.

I checked this against real filings. Ambience Healthcare ($70M), Viz.ai and Nabla
all filed under "Other Technology". Meanwhile the Health Care categories turned out
to be full of surgical robots, neuromodulation devices, drug companies, a
prescription discount card, and a house in Wayzata, Minnesota.

So the search covers Technology too. That costs volume — roughly 350 extra filings
a month against 150 healthcare ones, and every one gets looked up and judged.
There's no cheaper shortcut, because names like "Abridge" and "Nabla" tell you
nothing. If it's worth finding, it has to be looked up to be found.

Adding another area is one more file in `config/`. It shows up in the website's
dropdown straight away, and it roughly doubles what a day costs to run.

## Running it

```bash
python3.11 -m venv .venv          # 3.11+, for `str | None` annotations
.venv/bin/pip install -r requirements.txt

cp .env.example .env              # then fill in the keys
```

Two keys are needed and both are documented in [.env.example](.env.example):
`TAVILY_API_KEY` to find out what a company does, and `OPENROUTER_API_KEY` to judge
whether it fits.

Email is optional and needs `SMTP_USER` and `SMTP_PASSWORD`. For Gmail that has to
be an **App Password**, not your normal password — that's the mistake everyone
makes, so the error message says so explicitly. Oracle Cloud blocks outbound port
25, but 587 works, so Gmail over STARTTLS is fine.

### The radar

```bash
# default window is three days, so Monday still catches Friday
.venv/bin/python -m src.cli run

# any window, and email the result
.venv/bin/python -m src.cli run --start 2026-06-01 --end 2026-06-15 --send

# a rehearsal that doesn't use up the novelty of what it looks at
.venv/bin/python -m src.cli run --dry-run

# what got decided, and why
.venv/bin/python -m src.cli candidates --verdict fits
.venv/bin/python -m src.cli candidates --company Genomenon
.venv/bin/python -m src.cli status
```

Re-running a date range is always safe. Deduplication is exact, so overlapping
windows cost nothing except a line telling you what got skipped.

### On a schedule

```
MAILTO=""
RADAR_SEND=1
0 13 * * 1-5 /home/opc/deal-radar/scripts/daily.sh
```

Weekdays at 13:00 UTC. Weekdays only, because EDGAR doesn't publish at weekends.
Email is opt-in via `RADAR_SEND` so a missing mail password can't fail a run whose
actual work succeeded.

## The website

```bash
./scripts/web.sh                  # API on 8100, site on 3100
```

Then from your own machine:

```bash
ssh -L 3100:localhost:3100 oci
```

Ports 3100 and 8100 rather than 3000 and 8000, so it doesn't clash with anything
else on the same server.

The page has a domain dropdown, date pickers limited to the filings actually on
record, verdict filters, an unread-only toggle, and a question box at the bottom.

Rows you've read go grey and lose their coloured edge, unread ones keep it. That
contrast is the whole point — your eye should find the unread ones without reading
anything. Reading gets recorded when you open a row rather than when the page
loads, so the count tracks attention instead of delivery.

Opening a row shows what the company does, its website, the officers and directors
with their roles and where they're based, how much they're raising against how much
has sold, how many investors, when it was incorporated, entity type, jurisdiction,
and a link to the filing so you can check any of it yourself.

The question box only answers from judgements already recorded. It has no tools at
all, so it can't search or research anything — that's deliberate, and the page says
so underneath.

### Sharing it

```bash
printf 'SHARE_USER=review\nSHARE_PASSWORD=...\n' > web/.env.local
./scripts/share.sh
```

That serves the production build through a Cloudflare tunnel. No firewall changes
and no open ports, because cloudflared connects outward.

The password isn't optional and the script won't publish without one. The question
box spends money on every request and marking things read is a write, so an
unprotected URL is somebody else's ability to run up a bill. `share.sh` checks the
site actually returns 401 before opening the tunnel, rather than assuming the gate
works. The question box is also capped at sixty questions an hour, so a runaway
becomes a refusal instead of a bill.

The URL is temporary and different every time.

## Scripts

| Script | What it's for |
|---|---|
| `scripts/daily.sh` | one run, for cron; logs the email and its own commentary |
| `scripts/web.sh` | the API and site locally, in tmux |
| `scripts/share.sh` | production build behind a password, on a public URL |
| `scripts/diagnose.py` | every company with its evidence and why it got that verdict |
| `scripts/backfill_detail.py` | re-fetch filing detail for rows saved before it was stored |
| `scripts/rejudge.py` | re-judge stored rows after the prompt or verdicts change |

`diagnose.py` earns its keep. A radar that rejects everything looks exactly like a
broken one unless you can read the reasoning. The first live run rejected all six
companies — correctly, as it turned out, but the only way to know that was to read
why.

`rejudge.py` matters whenever the prompt changes, because stored rows still carry
verdicts from the old rules. It looks the companies up again rather than just
relabelling them, since a verdict reached on missing evidence deserves another look
at the evidence.

## Layout

| Module | What it does |
|---|---|
| [src/edgar.py](src/edgar.py) | EDGAR search and Form D parsing; the fetcher is injectable so tests stay offline |
| [src/normalize.py](src/normalize.py) | company identity — canonical domain, normalised name |
| [src/seen.py](src/seen.py) | the seen-index, the schema, and migrations |
| [src/thesis.py](src/thesis.py) | what counts as interesting, and the free filters that run first |
| [src/enrich.py](src/enrich.py) | what a company actually does, since the filing never says |
| [src/judge.py](src/judge.py) | the one step where a model forms an opinion |
| [src/candidates.py](src/candidates.py) | every judgement and its reasoning, queryable |
| [src/pipeline.py](src/pipeline.py) | the run, and the ordering rules that keep it safe |
| [src/digest.py](src/digest.py) | the message someone actually reads |
| [src/delivery.py](src/delivery.py) | email over SMTP; a Slack path exists but has never been used |
| [src/chat.py](src/chat.py) | answering questions from stored judgements, with no tools |
| [src/api.py](src/api.py) | HTTP for the website; almost entirely read-only |
| [src/cli.py](src/cli.py) | the command surface |
| [web/](web/) | the website — Next.js, types generated from the API |

Frontend types come from the API's schema, so `src/models.py` is the only place a
field gets defined and there's nothing to drift:

```bash
cd web && npm run gen:types      # needs the API running
```

That's caught real bugs. A Pydantic field with a `default_factory` isn't "required"
in the schema, so lists arrive typed as possibly-missing and the compiler refuses to
let you use them unguarded. And a `@property` on a Pydantic model **isn't sent over
the wire at all**, so `is_unread` and `filing_url` never reach the browser — they get
worked out there instead.

## Where things are kept

```
data/radar.sqlite        the seen-index, and every judgement with its reasoning
config/*.yaml            one file per area — edit these after talking to investors
outputs/digests/*.md     what got sent, so you can check an email later
outputs/logs/radar.log   what each scheduled run did
web/.env.local           credentials for sharing (git-ignored)
```

There are two tables. `seen_company` answers "have I come across this company?" and
does nothing else. `candidate` answers "what did I decide, and why?" — the question
you actually ask six months later, and the one that used to vanish the moment an
email went out. It's keyed on the filing rather than the company, because a company
can file more than once and each filing gets judged on its own evidence.

### Changing the schema

The database updates itself every time you connect. `CREATE TABLE IF NOT EXISTS`
does nothing to a table that already exists, so new columns have to be added
explicitly in `MIGRATIONS` or a deployed database quietly won't have them.

The order matters and it's easy to get wrong: **tables, then columns, then
indexes.** You can't index a column that hasn't been added yet, so one big schema
script breaks on any database older than its newest column. The migration tests
build a deliberately out-of-date database for this reason — a fresh one passes
happily and hides the bug.

## Things I deliberately didn't do

- **No model calls in the data layer.** Fetching, filtering, deduplicating and
  saving are ordinary code, so they stay testable offline. Judgement — is this a
  company, does it fit — is the model's job.
- **No search box.** Search finds what's already been written about, which is the
  latest possible tier. It'd be convenient and it'd make the sourcing worse.
- **No scraping of sources that don't allow it.** People moving jobs is the
  strongest early signal there is, and it's off the table because it means
  LinkedIn.
- **No score for how good an investment something is.** Software can measure
  whether the research is well evidenced. Whether a company is worth backing is the
  analyst's call, and a number computed in Python would just launder an opinion.

## Where it's got to

Runs end to end against live EDGAR, on a schedule, emails the result, and has a
website behind a password. **207 tests, none of which touch the network.**

Across 1 June to 17 July 2026, 202 companies seen:

```
fits 5   ·   maybe 1   ·   unknown 15   ·   no_fit 116
```

The five that fit, all found from raw filings:

| Company | Raise | What they do |
|---|---|---|
| Proxima Bio | $91.5M | AI drug discovery, proximity-based therapeutics |
| MemryHealth | $3M | EHR for post-acute care, documentation automation |
| Pretura Health | $2.5M | emergency department workflow coordination |
| PeriOp Ortho | $1.6M | orthopedic surgery care coordination |
| 1104Health | undisclosed | oncologist collaboration and trial software |

### What the real data changed

Six things I'd got wrong, and only real filings showed it.

**The healthcare filter was excluding healthcare software.** Covered above. Easily
the worst one — the free shortcut was filtering out exactly what it was supposed to
find.

**A $39 offering exists.** Hence a minimum.

**But rejecting filings with no stated amount was worse.** Form D lets companies
leave the amount open, and that rule quietly dropped three real companies inside a
single ten-day window. A missing number isn't evidence of a token raise, and for a
radar, missing a company is the failure that actually matters.

**Half the maybes weren't maybes.** Twelve out of twenty meant "couldn't find out".
Hence the fourth verdict.

**Enrichment was reading legal boilerplate.** Search returns whichever page matched
the company name, and that's very often the privacy policy or the leadership team —
pages on the right website that describe nothing. Preferring the shallowest
non-boilerplate page turned unanswerable shrugs into decisions. PreventiveMD went
from its terms page to its homepage, which revealed a GLP-1 telehealth service, and
that's a clean rejection rather than a maybe.

**An `ElementTree` element with no children is falsey.** So `find_element(...) or
fallback` quietly takes the fallback even when it found something, and `if offering`
treats an empty `<offeringData/>` as missing. I'd done this in two places, and both
passed on the sample filing by luck.

### Still to do

- Slack instead of email — `delivery.py` shells out to `hermes send`, but that path
  has never actually run because Slack was never credentialed. Treat it as
  untested.
- Monitoring beyond a fixed daily window
- More areas than healthcare

**And the thing that decides whether any of this is real:** the thesis is still a
placeholder. The criteria are in `config/thesis.yaml` and they're a reasonable
guess, nothing more. What belongs there is an actual mandate — stage, geography,
cheque size, and what rules a company out in the first thirty seconds. That comes
from talking to investors, not from writing more code.

Every verdict above was measured against criteria no investor has looked at yet.
