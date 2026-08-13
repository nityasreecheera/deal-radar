# Developing Deal Radar

Everything technical. For what the product is and who it's for, see
[README.md](README.md).

## The design rule

**Judgement from the model, mechanics from code, validation in between.**

Here's the whole thing, with the important line marked:

```
CRON, weekdays — nothing has to be running
  │
  1. FETCH      SEC EDGAR full-text search → Form D filings
  │             stdlib XML parsing, no model involved
  │
  2. FILTER     thresholds, amendments, investment vehicles
  │             free, so it runs before anything that costs money
  │
  3. DEDUPE     SQLite index, by canonical domain then normalised
  │             name.  ← this is the actual product
  │
  ├──────────── only companies never seen before get past here
  │
  4. ENRICH     what does this company actually do?
  │             a filing never says, so it has to be looked up
  │
  5. JUDGE      does it fit, and one line on what they do
  │             ← the only step where a model has an opinion
  │
  6. RECORD     write to the seen-index and the judgement table
  │
  7. EMAIL      render and send
  │
  └──────────── the website and question box read the same tables
```

Steps 1–3 and 6 are ordinary code with no model anywhere near them, which is why
all 258 tests run offline. Step 5 is the one place something forms an opinion, and
whatever it returns gets schema-validated before anything is written. If the model
returns nonsense the run records a problem and moves on. It never guesses a verdict
and never marks that company as seen, so tomorrow gets another attempt.

## Where the data comes from

Which *tier* a source sits in matters more than which source it is.

**Too late to be useful** — press, newsletters, podcasts, most of Twitter. By the
time something's here every fund has seen it.

**Everyone at once** — YC's directory and Demo Day, Techstars batches, Product Hunt.
Good and already vetted, but everyone sees them the same day, so the only edge left
is how fast you reply.

**Early and noisy, which is where the edge actually is:**

- **People moving jobs.** A good operator leaving a good company is a company about
  to exist. Months earlier than anything else, and the hardest to get honestly,
  because it means LinkedIn and their terms don't allow scraping.
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
worth having if something filters them.

**Paid, and mostly about money** — PitchBook, Crunchbase. Valuations, round history,
comparables. Hard to replace, easy to put off.

## What it depends on outside

| Service | What it gives us | Cost |
|---|---|---|
| **SEC EDGAR** | the filings themselves | free, no signup, no key |
| **Tavily** | web search, to find out what a company does | free tier covers ~500/month |
| **OpenRouter** | the model that judges each company | roughly $2/month at current volume |

EDGAR is the one that matters and it's the one that's free. It needs a User-Agent
header with a contact address or it returns 403.

The other two are replaceable. Tavily is just a search API, and the judge talks to
an OpenAI-compatible endpoint, so pointing `LLM_BASE_URL` somewhere else is a config
change rather than a rewrite.

## The stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | it's mostly I/O and parsing |
| Seen-index | SQLite (stdlib) | exact lookups, thousands of rows, hit on every filing |
| Schemas | Pydantic | the validation boundary between model and disk |
| HTTP | httpx | — |
| Filing parsing | `xml.etree` (stdlib) | Form D is small, structured XML |
| Enrichment | Tavily | finding out what a company does |
| Judging | OpenRouter, structured output | short verdict per filing, no agent loop needed |
| Email | `smtplib` (stdlib) | Gmail over STARTTLS on 587 |
| API | FastAPI | the OpenAPI schema generates the frontend types |
| Website | Next.js + Tailwind | types come from that schema |
| Scheduling | cron | survives reboots, needs nothing else running |

### Three decisions worth explaining

**A direct API call rather than an agent.** Scoring 130 filings a day is a short
structured verdict per filing. An agent loop with tool access would take far longer
per company and add nothing. Research needs steering and follow-up; this doesn't.

**SQLite rather than files on disk.** Everything else here would be fine as JSON, but
the seen-index gets queried on every single filing and grows into the thousands. It's
also the one thing that has to be *provably* right — "skipped 64 you've already seen"
is only worth printing if it's true.

**No LLM in the data layer, on purpose.** It would have been easier to let a model do
the filtering and deduplicating too. But then nothing is testable without a network
and a bill, and "have I seen this company?" becomes a question with a probabilistic
answer. That's the wrong kind of answer for the one thing the product depends on.

## What it searches, and the mistake underneath

Right now: **healthcare AI and clinical software** — trials, diagnostics, care
coordination, health data.

*Health Care* is one of the SEC's own industry categories on Form D, so filtering on
it looked like a free way to narrow things. It isn't, because healthcare **software**
files under *Technology* instead.

Checked against real filings: Ambience Healthcare ($70M), Viz.ai and Nabla all filed
under "Other Technology". Meanwhile the Health Care categories turned out to be full
of surgical robots, neuromodulation devices, drug companies, a prescription discount
card, and a house in Wayzata, Minnesota.

So the search covers Technology too. That costs volume — roughly 350 extra filings a
month against 150 healthcare ones, and every one gets looked up and judged. There's
no cheaper shortcut, because names like "Abridge" and "Nabla" tell you nothing.

Adding another area is one more file in `config/`. It shows up in the website's
dropdown straight away, and roughly doubles what a day costs to run.

## Running it

```bash
python3.11 -m venv .venv          # 3.11+, for `str | None` annotations
.venv/bin/pip install -r requirements.txt

cp .env.example .env              # then fill in the keys
```

Two keys are needed, both documented in [.env.example](.env.example):
`TAVILY_API_KEY` and `OPENROUTER_API_KEY`.

Email is optional and needs `SMTP_USER` and `SMTP_PASSWORD`. For Gmail that has to be
an **App Password**, not your normal password — that's the mistake everyone makes, so
the error message says so explicitly. Oracle Cloud blocks outbound port 25, but 587
works.

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

Weekdays at 13:00 UTC, because EDGAR doesn't publish at weekends. Email is opt-in via
`RADAR_SEND` so a missing mail password can't fail a run whose actual work succeeded.

## The website

```bash
./scripts/web.sh                  # API on 8100, site on 3100
```

Then from your own machine:

```bash
ssh -L 3100:localhost:3100 oci
```

Ports 3100 and 8100 rather than 3000 and 8000, so it doesn't clash with anything else
on the same server.

Reading gets recorded when the company's own page opens, rather than when the list
loads, so the count tracks attention instead of delivery — and arriving by a direct
link counts too.

Two routes: `/` is the list, `/company/[accession]` is one company. **List filters
live in the URL, not in state.** That is what makes the back button land on the list
you were actually looking at rather than the default view, and it makes a filtered
list something you can send someone. The row passes the current query string along
as `?from=`, and the back link reads it.

`useSearchParams` forces client rendering up to the nearest Suspense boundary, and a
production build fails outright without one — hence the boundary around the list.
Dynamic route params arrive as a Promise in this version of Next and are unwrapped
with React's `use()`.

The question box has no tools at all, so it can't search or research anything. That's
a capability restriction, not an instruction — there's nothing to talk it out of.

### Signing in, and the two ways past the gate

A **session cookie** for people and **Basic auth** for scripts, both checked in
`web/src/proxy.ts`.

Basic auth has no logout. The browser caches the credentials for the life of the
window and there is no standard way to ask it to forget them, so a sign-out button
on top of Basic auth is a button that does nothing. Hence the cookie: an issue time
plus an HMAC of that time, keyed on `SHARE_PASSWORD`. Nothing is stored server-side,
and changing the password invalidates every session already issued.

Basic auth stays because `curl`, the deploy checks and `share.sh` have no business
with a login form.

Unauthenticated requests are answered differently on purpose: `/api/*` gets a 401,
a page gets a redirect to `/login`. `share.sh` refuses to publish until an
unauthenticated request is rejected, and a redirect is not a rejection it can tell
apart from a working site — so it checks `/api/meta` rather than the homepage.

**Redirects out of the auth routes are relative.** Behind the tunnel `request.url`
is the VM's own address, so `NextResponse.redirect(new URL(path, request.url))`
sends people to `https://localhost:3100/…`. That works perfectly while testing on
the VM and is a dead link for everyone else.

### Sharing it

The site lives at a permanent address:

```
https://radar.humpback-pleco.ts.net
```

That's a Tailscale Funnel. `tailscaled` dials outward and Tailscale terminates
HTTPS, so there is still no open port and no security-list change on the VM — same
property as the old Cloudflare tunnel, but the name doesn't change on restart.

```bash
sudo tailscale funnel --bg 3100      # on
sudo tailscale funnel --https=443 off  # off
```

The tailnet name is bound to the certificate once Funnel issues one, so it can't be
renamed again. `radar.humpback-pleco` is what it is.

The password gate is unchanged and still not optional. It's Next.js middleware
reading `SHARE_USER` and `SHARE_PASSWORD` from `web/.env.local`. The question box
spends money on every request and marking things read is a write, so an unprotected
URL is somebody else's ability to run up a bill. The chat endpoint is capped at sixty
questions an hour, so a runaway becomes a refusal instead of a bill.

`scripts/share.sh` still exists and still opens a throwaway Cloudflare tunnel. It's
only useful now if you want a second, disposable URL — the permanent one is served
by systemd and needs no script.

### Surviving a reboot

The API and the website run as **user** systemd services, not from tmux:

```bash
systemctl --user status radar-api radar-web
systemctl --user restart radar-web
journalctl --user -u radar-web -n 50
```

They're user services rather than system ones because SELinux on Oracle Linux
refuses to let `init_t` execute anything labelled `user_home_t` — a system unit
pointing at `/home/opc/deal-radar/.venv/bin/uvicorn` dies with a bare "Permission
denied" that looks nothing like an SELinux problem. Running them in the user manager
sidesteps it, and `loginctl enable-linger opc` is what makes the user manager start
at boot instead of at first login.

Verified by actually rebooting: the VM came back and the public URL answered on its
own in about ninety seconds, with no login and nothing started by hand.

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
companies, correctly as it turned out, but the only way to know that was to read why.

`rejudge.py` matters whenever the prompt changes, because stored rows still carry
verdicts from the old rules. It looks the companies up again rather than just
relabelling them, since a verdict reached on missing evidence deserves another look at
the evidence.

## Layout

Each module does one job. `pipeline.py` is the only thing that knows the order:

```
cron
 └─ cli.py                      the command surface
     └─ pipeline.py             runs everything in order
         ├─ edgar.py            → SEC EDGAR      get the filings
         ├─ thesis.py           → config/*.yaml  throw out the junk, free
         ├─ seen.py             → SQLite         "have we seen this before?"
         ├─ enrich.py           → Tavily         "what do they actually do?"
         ├─ judge.py            → OpenRouter     "is this interesting?"
         ├─ candidates.py       → SQLite         write down what was decided
         ├─ funding.py          → SEC EDGAR      every raise a company has filed
         ├─ people.py           → SQLite         who else a person appears with
         ├─ digest.py                            write the short list
         └─ delivery.py         → SMTP           email it
```

The website is a separate path and never runs any of that. It only reads what has
already been written:

```
browser → web/ → api.py → SQLite
                   └─ chat.py → OpenRouter   (answers from stored rows only)
```

Two things follow. The radar works with nothing running and no browser open. And
nothing you do on the website can change what the radar decided — the only thing it
writes is whether you have read a row.

| Module | What it does |
|---|---|
| [src/edgar.py](src/edgar.py) | EDGAR search and Form D parsing; the fetcher is injectable so tests stay offline |
| [src/normalize.py](src/normalize.py) | company identity — canonical domain, normalised name |
| [src/seen.py](src/seen.py) | the seen-index, the schema, and migrations |
| [src/thesis.py](src/thesis.py) | what counts as interesting, and the free filters that run first |
| [src/enrich.py](src/enrich.py) | what a company actually does, since the filing never says |
| [src/judge.py](src/judge.py) | the one step where a model forms an opinion |
| [src/candidates.py](src/candidates.py) | every judgement and its reasoning, plus the analyst's own call on top |
| [src/funding.py](src/funding.py) | a company's whole filing history, not just today's |
| [src/people.py](src/people.py) | officers and directors, and who else they appear with |
| [src/pipeline.py](src/pipeline.py) | the run, and the ordering rules that keep it safe |
| [src/digest.py](src/digest.py) | the message someone actually reads |
| [src/delivery.py](src/delivery.py) | email over SMTP; a Slack path exists but has never been used |
| [src/chat.py](src/chat.py) | answering questions from stored judgements, with no tools |
| [src/api.py](src/api.py) | HTTP for the website; almost entirely read-only |
| [src/cli.py](src/cli.py) | the command surface |
| [web/](web/) | the website — Next.js, types generated from the API |
| [web/src/proxy.ts](web/src/proxy.ts) | the password gate; `middleware.ts` is deprecated in Next 16 and renamed to `proxy` |

Frontend types come from the API's schema, so `src/models.py` is the only place a field
gets defined and there's nothing to drift:

```bash
cd web && npm run gen:types      # needs the API running
```

That's caught real bugs. A Pydantic field with a `default_factory` isn't "required" in
the schema, so lists arrive typed as possibly-missing and the compiler refuses to let you
use them unguarded. And a `@property` on a Pydantic model **isn't sent over the wire at
all**, so `is_unread` and `filing_url` never reach the browser — they get worked out
there instead.

## Where things are kept

```
data/radar.sqlite        the seen-index, and every judgement with its reasoning
config/*.yaml            one file per area — edit these after talking to investors
outputs/digests/*.md     what got sent, so you can check an email later
outputs/logs/radar.log   what each scheduled run did
web/.env.local           credentials for sharing (git-ignored)
```

`seen_company` answers "have I come across this company?" and does nothing else.
`candidate` answers "what did I decide, and why?" — the question you actually ask six
months later. It's keyed on the filing rather than the company, because a company can
file more than once and each filing gets judged on its own evidence. `person` and
`funding_round` hold the cross-filing detail the website shows when you open a row.

### The analyst's verdict versus the model's

`user_verdict`, `user_note` and `decided_at` sit next to `verdict` rather than
replacing it. That separation is load-bearing for three reasons:

- `rejudge.py` rewrites `verdict` whenever the prompt changes. A human decision
  stored there would be wiped without a trace.
- Disagreement is the only real evidence of whether the thesis is any good. A long
  `/api/disagreements` list means `config/thesis.yaml` doesn't say what the analyst
  means, which is a config problem, not a code one.
- "The filter said no, you said yes" is itself worth showing.

Everything that reads a verdict uses `COALESCE(user_verdict, verdict)` — including
the list filters, or a company someone re-labelled would vanish from the label they
gave it. On the frontend the same rule lives in `effectiveVerdict()`, and every piece
of styling goes through it.

`effective_verdict` and `overridden` are Pydantic **computed fields**, not
properties. A `@property` isn't serialised and would never reach the browser, which
has already cost time twice on this project.

### Changing the schema

The database updates itself every time you connect. `CREATE TABLE IF NOT EXISTS` does
nothing to a table that already exists, so new columns have to be added explicitly in
`MIGRATIONS` or a deployed database quietly won't have them.

The order matters and it's easy to get wrong: **tables, then columns, then indexes.**
You can't index a column that hasn't been added yet, so one big schema script breaks on
any database older than its newest column. The migration tests build a deliberately
out-of-date database for this reason — a fresh one passes happily and hides the bug.

## What the real data changed

Seven things I'd got wrong, and only live filings showed it.

**The healthcare filter was excluding healthcare software.** Covered above. Easily the
worst one — the free shortcut was filtering out exactly what it was supposed to find.

**A $39 offering exists.** Hence a minimum.

**But rejecting filings with no stated amount was worse.** Form D lets companies leave
the amount open, and that rule quietly dropped three real companies inside a single
ten-day window. A missing number isn't evidence of a token raise, and for a radar,
missing a company is the failure that actually matters.

**Half the maybes weren't maybes.** Twelve out of twenty meant "couldn't find out."
Hence the fourth verdict.

**Enrichment was reading legal boilerplate.** Search returns whichever page matched the
company name, and that's very often the privacy policy or the leadership team. Preferring
the shallowest non-boilerplate page turned unanswerable shrugs into decisions.
PreventiveMD went from its terms page to its homepage, which revealed a GLP-1 telehealth
service, and that's a clean rejection rather than a maybe.

**An `ElementTree` element with no children is falsey.** So `find_element(...) or fallback`
quietly takes the fallback even when it found something, and `if offering` treats an empty
`<offeringData/>` as missing. I'd done this in two places, and both passed on the sample
filing by luck.

**A failed search looked exactly like a quiet day.** EDGAR's search endpoint 500s
under load. On 7 and 11 August it failed on every category, and both emails said
"nothing new matched the thesis" — when nothing had been searched at all. That is the
one lie this thing could tell that would actually matter, because it is indistinguishable
from working. Fixed in two parts: 5xx and timeouts now retry with backoff (403 doesn't,
since a bad User-Agent will still be bad in eight seconds), and any category that still
can't be reached is named in the email above the fold. Re-running the failed window
afterwards turned up 48 companies that had been missed, one of which fit.

**`dateOfFirstSale` is nested under `typeOfFiling`, not `offeringData`.** I guessed
the flat path, wrote the test fixture to match my guess, and shipped a parser that
returned None for every real filing while the suite stayed green. Fixtures invented
from an assumption test the assumption, not the document. The fixture is now the
shape EDGAR actually serves.

**`thesis.domain` is the label rows are stored under; `thesis.name` is prose.**
"Healthcare" versus "Healthcare AI and clinical software". I filtered the category
counts on `name`, which matches no row ever — silently, so the new lines simply never
appeared in the email and everything looked like it worked. Anything querying by theme
must use `domain`. There is a test naming both.

**Amendments were being thrown away entirely.** Proxima Bio opened at $88.5M in January
and amended to $91.5M in June; only the first number was being reported, so the round
looked smaller than it was and the fact that it filled was invisible. Amendments now plot,
drawn hollow on a dashed line so they don't read as a second raise, and totals still ignore
them so nothing double-counts.

## Still to do

- `issuerSize/revenueRange` is in every filing and unused. "No Revenues" versus
  "$1,000,000 - $4,999,999" is a stage signal for free.
- Slack instead of email — `delivery.py` shells out to `hermes send`, but that path has
  never actually run because Slack was never credentialed. Treat it as untested.
- Monitoring beyond a fixed daily window.
- More areas than healthcare.

**And the thing that decides whether any of this is real:** the thesis is still a
placeholder. The criteria are in `config/thesis.yaml` and they're a reasonable guess,
nothing more. What belongs there is an actual mandate — stage, geography, cheque size, and
what rules a company out in the first thirty seconds. That comes from talking to investors,
not from writing more code.
