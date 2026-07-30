# Deal Radar

Every morning, a short list of companies that just became visible and that you
have never seen before, ranked against what you actually invest in.

It is not a search tool and not a database. It is a filter with a memory.

## The problem it solves

An investment analyst is not short of information. They are drowning in it. The
things that actually hurt are these:

1. **Remembering, not finding.** *"I saw a company like this eight months ago —
   who was it?"* The notes are in email, in a CRM nobody updates, in someone's
   head.
2. **Screening is repetitive but still needs judgement.** Every new company needs
   the same lookups: what do they do, what stage, where, who runs it, is this even
   in our box. Twenty to forty minutes, and nine times out of ten the answer is no.
3. **Spotting who is about to be interesting.** This is the actual craft, and the
   hardest thing to systematise.
4. **Nobody wrote the mandate down.** Everyone "knows" what the fund invests in,
   but not in a form you can apply, so screening quality depends on who happens to
   be doing it.
5. **The reasoning disappears.** Passing on a company is the most information-rich
   moment in the job. Six months later it raises at 5× and nobody remembers why
   the answer was no.
6. **Nobody knows where the relationship stands.** Have we spoken to them? Who?
   When? What did we say?

Problems 1, 5 and 6 are the dullest and the least solved. That is where this
starts.

## Why not just use Crunchbase

Crunchbase has more data than this will ever have, and that is not worth competing
on. Two things it cannot do:

- **It does not remember what you have already seen.** Every search scrolls past
  the same companies you looked at and rejected last year.
- **It does not know what you care about.** You describe that again, in filters,
  every session.

| Crunchbase | Deal Radar |
|---|---|
| You go to it | It comes to you |
| Search, scroll, filter | A short list, already filtered |
| You spot the stale names yourself | Stale names never appear |
| 30–45 minutes | 2 minutes |

Crunchbase is a supermarket. Everything is there and you do the shopping. This is
more like someone who knows what is in your fridge.

They are not really competitors. Crunchbase could be a *source* for this. The
product is the filter and the memory on top, whatever database sits underneath.

### About speed — the honest version

**This does not get data faster than Crunchbase.** They ingest the same public
filings automatically, within a day or two, and anything a company announces
publicly reaches them the same day. Claiming earlier data would not survive one
follow-up question.

There is a narrow exception. Small unannounced raises — a $2M seed with no press
release — get curated slowly everywhere, so there this can genuinely be days
ahead. Real, but niche. Not a headline.

The claim that does hold is different. Data arriving is not the bottleneck; *you
finding out* is. Something can sit in Crunchbase for a week while you have no idea,
because you have not run the right search. Here it arrives already filtered, so you
know days sooner even when the underlying data landed at the same moment.

**Not faster data. Faster to the person who needs it.**

## Where the data comes from

Which *tier* a source sits in matters more than which source it is.

**Too late to be useful** — press, newsletters, podcasts, most of Twitter. By the
time something appears here, every fund has seen it. Good for understanding the
narrative, useless for finding companies first.

**Everyone at once** — Y Combinator's directory and Demo Day, Techstars batches,
Product Hunt. Genuinely good and pre-vetted, but everyone sees them the same day,
so the only edge left is how fast you reply.

**Early and noisy — where the edge actually is:**

- **People moving.** A strong operator leaving a good company is a company about
  to exist. Months earlier than anything else. Also the hardest to get honestly,
  because it means LinkedIn, and their terms prohibit scraping.
- **Hiring.** A first enterprise sales hire means moving upmarket. A first ten
  engineers means they raised.
- **Regulatory filings.** A US company files SEC Form D when it raises, sometimes
  before announcing anything. Public, structured, free. **This is what the radar
  currently uses.**
- **Launch HN and Show HN.** A company's earliest public moment, described by its
  own founder.
- **Developer traction** — GitHub stars, package downloads — for developer tools.
- **Research papers.** For AI, authors and lab affiliations predict companies by a
  year or more.

This tier needs software precisely *because* it is noisy. Early signals are only
worth having if something filters them, and filtering by hand every day is not
sustainable.

**Paid, and mostly about the money** — PitchBook, Crunchbase. Valuations, round
history, comparables. Hard to replace, easy to postpone.

## How it works

```
every weekday  → pull new SEC filings
               → drop anything already seen
               → look up what each company actually does
               → judge it against the thesis
               → email a short list
```

The email is the product. A radar you have to remember to open is a radar you
check twice and then forget.

Email rather than Slack because it needs a password and nothing else. No
workspace, no app to create, no admin approval.

There are three places to look, each doing one job:

- **The email** — the daily habit. It comes to you.
- **The website** — where you go when something looks worth a closer look, and
  where you mark things as read.
- **Talking to the agent** — for research and follow-up, where judgement helps.

A chatbot cannot be the main way in. You cannot ask about a company you do not
know exists, and that is the whole problem.

### The four verdicts

Every company gets one of four. The fourth exists because of what real data looked
like, not because four is tidier than three.

| Verdict | What it means | Shown in the email? |
|---|---|---|
| `fits` | clearly within the thesis | yes |
| `maybe` | we know what they do, the fit is arguable | yes |
| `unknown` | we never found out what they do | counted only |
| `no_fit` | clearly outside it | counted only |

`maybe` and `unknown` started as one bucket. In practice twelve of twenty maybes
turned out to mean "we could not find out" — a placeholder website, boilerplate,
nothing at all. Reading those as judgements filled half the email with shrugs,
which is the quickest way to make someone stop reading it. An analyst treats them
differently anyway: a maybe is worth a look, an unknown is worth a search.

The judge also writes **one line on what the company does**, kept separate from its
reason for the verdict. The reason explains the decision; the summary describes the
business. When they were the same field, the only description available was a raw
search snippet, which is usually legal boilerplate.

## What it looks for

Right now: **healthcare AI and clinical software** — trials, diagnostics, care
coordination, health data.

An early assumption here was wrong, and it is worth writing down. *Health Care* is
one of the SEC's own industry categories on Form D, which looked like a free way to
narrow things down. It is not, because healthcare **software** files under
*Technology* instead.

That was checked against real filings. Ambience Healthcare ($70M), Viz.ai and Nabla
all filed under "Other Technology". Meanwhile the Health Care categories turned out
to contain surgical robots, neuromodulation devices, drug companies, a prescription
discount card, and a house in Wayzata, Minnesota.

So the search covers Technology too. That costs volume — roughly 350 extra filings
a month against 150 healthcare ones, and every one of them gets looked up and
judged. There is no cheaper shortcut, because names like "Abridge" and "Nabla" tell
you nothing. Anything worth finding has to be looked up to be found.

Adding another area means one more file in `config/`. It appears in the website's
dropdown immediately, and it roughly doubles what a day costs to run.

## Running it

```bash
python3.11 -m venv .venv          # 3.11 or newer, for `str | None` annotations
.venv/bin/pip install -r requirements.txt

cp .env.example .env              # then fill in the keys
```

Two keys are required, both documented in [.env.example](.env.example):
`TAVILY_API_KEY` to find out what a company does, and `OPENROUTER_API_KEY` to judge
whether it fits.

Email is optional and needs `SMTP_USER` and `SMTP_PASSWORD`. For Gmail that has to
be an **App Password**, not your account password — that is the mistake everybody
makes, and the error message says so. Oracle Cloud blocks outbound port 25, but 587
works, so Gmail over STARTTLS is fine.

### The radar

```bash
# the default window: three days, so a Monday still catches Friday
.venv/bin/python -m src.cli run

# any window you like, and email the result
.venv/bin/python -m src.cli run --start 2026-06-01 --end 2026-06-15 --send

# a rehearsal that does not use up the novelty of what it looks at
.venv/bin/python -m src.cli run --dry-run

# what was decided, and why
.venv/bin/python -m src.cli candidates --verdict fits
.venv/bin/python -m src.cli candidates --company Genomenon
.venv/bin/python -m src.cli status
```

Re-running a date range is always safe. Deduplication is exact, so overlapping
windows cost nothing but a line saying what was skipped.

### On a schedule

```
MAILTO=""
RADAR_SEND=1
0 13 * * 1-5 /home/opc/deal-radar/scripts/daily.sh
```

Weekdays at 13:00 UTC — weekdays only, because EDGAR does not publish at weekends.
Email is opt-in through `RADAR_SEND`, so a missing mail password cannot fail a run
whose real work succeeded.

## The website

```bash
./scripts/web.sh                  # API on 8100, site on 3100
```

Then from your own machine:

```bash
ssh -L 3100:localhost:3100 oci
```

Ports 3100 and 8100 rather than 3000 and 8000, so it does not clash with anything
else on the same server.

The page has a domain dropdown, date pickers limited to the filings actually on
record, verdict filters, an unread-only toggle, and a question box at the bottom.

Rows you have read go grey and lose their coloured edge. Unread ones keep it. That
contrast is the point — your eye should find the unread ones without reading a
word. Reading is recorded when you open a row, not when the page loads, so the
count reflects attention rather than delivery.

Opening a row shows what the company does, its website, the officers and directors
with their roles and where they are based, how much is being raised against how
much has sold, how many investors, when it was incorporated, entity type,
jurisdiction, and a link to the filing itself so you can check any of it at source.

The question box answers only from judgements already recorded. It has no tools at
all, so it cannot search or research — that is deliberate, and the page says so
underneath.

### Sharing it

```bash
printf 'SHARE_USER=review\nSHARE_PASSWORD=...\n' > web/.env.local
./scripts/share.sh
```

That serves the production build through a Cloudflare tunnel. No firewall change
and no open port, because cloudflared connects outward.

The password is not optional and the script refuses to publish without one. The
question box spends money on every request and marking things read is a write, so
an unprotected URL is somebody else's ability to run up a bill. `share.sh` checks
the site actually returns 401 before opening the tunnel rather than assuming the
gate works. The question box is also capped at sixty questions an hour, which turns
a runaway into a refusal.

The URL is temporary and different every time.

## Scripts

| Script | What it is for |
|---|---|
| `scripts/daily.sh` | one run, for cron; logs the email and its own commentary |
| `scripts/web.sh` | the API and site locally, in tmux |
| `scripts/share.sh` | production build behind a password, on a public URL |
| `scripts/diagnose.py` | every company with its evidence and why it was judged that way |
| `scripts/backfill_detail.py` | re-fetch filing detail for rows saved before it was stored |
| `scripts/rejudge.py` | re-judge stored rows after the prompt or verdicts change |

`diagnose.py` earns its keep. A radar that rejects everything looks exactly like a
broken one unless you can read the reasoning. The first live run rejected all six
companies — correctly, as it happened, but the only way to know that was to read
why.

`rejudge.py` matters whenever the prompt changes, because stored rows still carry
verdicts reached under the old rules. It looks the companies up again rather than
just relabelling them: a verdict reached on missing evidence deserves another look
at the evidence.

## Layout

| Module | What it does |
|---|---|
| [src/edgar.py](src/edgar.py) | EDGAR search and Form D parsing; the fetcher is injectable so tests stay offline |
| [src/normalize.py](src/normalize.py) | company identity — canonical domain, normalised name |
| [src/seen.py](src/seen.py) | the seen-index, the schema, and migration |
| [src/thesis.py](src/thesis.py) | what counts as interesting, and the free filters that run first |
| [src/enrich.py](src/enrich.py) | what a company actually does, since a filing never says |
| [src/judge.py](src/judge.py) | the one step where a model forms an opinion |
| [src/candidates.py](src/candidates.py) | every judgement and its reasoning, queryable |
| [src/pipeline.py](src/pipeline.py) | the run, and the ordering rules that keep it safe |
| [src/digest.py](src/digest.py) | the message someone actually reads |
| [src/delivery.py](src/delivery.py) | email over SMTP, or Slack through the agent |
| [src/chat.py](src/chat.py) | answering questions from stored judgements, with no tools |
| [src/api.py](src/api.py) | HTTP for the website; almost entirely read-only |
| [src/cli.py](src/cli.py) | the command surface |
| [web/](web/) | the website — Next.js, with types generated from the API |

Frontend types come from the API's schema, so `src/models.py` is the only place a
field is defined and there is nothing to drift:

```bash
cd web && npm run gen:types      # needs the API running
```

That has caught real bugs. A Pydantic field with a `default_factory` is not
"required" in the schema, so lists arrive typed as possibly-missing and the
compiler rejects using them unguarded. And a `@property` on a Pydantic model is
**not sent over the wire at all**, so `is_unread` and `filing_url` never reach the
browser and are worked out there instead.

## Where things are kept

```
data/radar.sqlite        the seen-index, and every judgement with its reasoning
config/*.yaml            one file per area — the files to edit after talking to investors
outputs/digests/*.md     what was sent, so an email can be checked later
outputs/logs/radar.log   what each scheduled run did
web/.env.local           credentials for sharing (ignored by git)
```

Two tables. `seen_company` answers "have I come across this company?" and does
nothing else. `candidate` answers "what did I decide, and why?" — the question
actually asked six months later, and the one that used to vanish the moment an
email was sent. It is keyed on the filing rather than the company, because a
company can file more than once and each filing is judged on its own evidence.

### Changing the schema

The database updates itself on every connect. `CREATE TABLE IF NOT EXISTS` does
nothing to a table that already exists, so new columns have to be added explicitly
in `MIGRATIONS` or a deployed database quietly lacks them.

The order matters and is easy to get wrong: **tables, then columns, then indexes.**
You cannot index a column that has not been added yet, so one big schema script
fails on any database older than its newest column. The migration tests build a
deliberately out-of-date database for this reason — a fresh one passes happily and
hides the bug.

## Things deliberately not done

- **No model calls in the data layer.** Fetching, filtering, deduplicating and
  saving are ordinary software, so they stay testable offline. Judgement — is this
  a company, does it fit — is the model's job.
- **No search box.** Search finds what has already been written about, which is the
  latest possible tier. It would be convenient and produce worse sourcing.
- **No scraping of sources that forbid it.** People moving jobs is the strongest
  early signal there is, and it is off the table because it means LinkedIn.
- **No score for how good an investment something is.** Software can measure
  whether research is well evidenced. Whether a company is worth backing is the
  analyst's call, and a number computed in Python would only launder an opinion.

## Where it has got to

Runs end to end against live EDGAR, on a schedule, emails the result, and has a
website behind a password. **207 tests, none of which touch the network.**

Across 1 June to 17 July 2026 — 202 companies seen:

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

### What real data changed

Six things in the original design were wrong, and only real filings showed it.

**The healthcare filter was excluding healthcare software.** Covered above. Easily
the most consequential mistake here — the free shortcut was filtering out exactly
what it was meant to find.

**A $39 offering exists.** So there is a minimum.

**But rejecting filings with no stated amount was worse.** Form D lets companies
leave the amount open, and that rule quietly dropped three real companies in a
single ten-day window. A missing number is not evidence of a token raise, and for a
radar, missing a company is the one failure that matters.

**Half the maybes were not maybes.** Twelve out of twenty meant "we could not find
out". Hence the fourth verdict.

**Enrichment was reading legal boilerplate.** Search returns whichever page matched
the company name, and that is very often the privacy policy or the leadership team
— pages on the right website that describe nothing. Preferring the shallowest
non-boilerplate page turned unanswerable shrugs into decisions. PreventiveMD moved
from its terms page to its homepage, which revealed a GLP-1 telehealth service — a
clean rejection rather than a maybe.

**An `ElementTree` element with no children is falsey.** So `find_element(...) or
fallback` silently takes the fallback even when it found something, and `if
offering` treats an empty `<offeringData/>` as absent. That was present twice, and
passed on the sample filing by luck.

### Still to do

- Slack as an alternative to email — the code is there, the credentials are not
- Monitoring beyond a fixed daily window
- More areas than healthcare

**And the thing that decides whether any of this is real:** the thesis is still a
placeholder. The criteria live in `config/thesis.yaml` and they are a reasonable
guess, nothing more. What belongs there is an actual mandate — stage, geography,
cheque size, and what rules a company out in the first thirty seconds. That comes
from talking to investors, not from writing more code.

Every verdict above was measured against criteria nobody in the industry has
looked at.
