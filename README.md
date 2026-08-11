# Deal Radar

Every weekday morning, a short email of companies that just filed to raise money,
that you've never seen before, filtered down to the ones worth your time.

Not a database and not a search tool. It's a filter that remembers.

## What you actually get

One email, around 5am. Usually four or five names. Each one has what the company
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

## Why not Crunchbase

Crunchbase has vastly more data than this will ever have, and that's not worth
competing on. It's a supermarket. Everything's there and you do the shopping.

Two things it can't do:

| | Crunchbase | Deal Radar |
|---|---|---|
| Getting to it | You go and search | It arrives |
| Companies you've rejected | Show up again every time | Never appear again |
| Your thesis | Re-entered as filters, every session | Written down once |
| Time per day | 30–45 minutes | 2 minutes |

**It's not faster data.** Crunchbase pulls the same public filings within a day or
two. The difference is when *you* find out. Something can sit in a database for a
week while you have no idea, because you never ran the right search.

They're not really competitors. Crunchbase could be a source *for* this. The part
that matters is the memory and the filter on top, whatever's underneath.

## What it's found

Running against live SEC filings from 1 June to 11 August 2026:

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

About **$2 a month**. SEC filings are free and public. Web search runs on a free
tier. The only real cost is the model that reads each company, and that's roughly
two dollars at this volume.

It runs on a small cloud server on a schedule. Nothing has to be open and nothing
has to be running. The site sits at a fixed address behind a password, and both it
and the daily run come back on their own after a reboot.

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

There's a question box at the bottom, but it only answers from companies already
judged. It can't search or research anything new, and the page says so. That's on
purpose: you can't ask about a company you don't know exists, and that's the whole
problem.

## What it deliberately won't do

- **It won't score how good an investment something is.** Software can tell you
  whether the research is well evidenced. Whether a company is worth backing is
  your call, and a number computed in Python would just launder an opinion as maths.
- **It won't guess.** If the model returns something malformed, the run records a
  problem and moves on. It never invents a verdict, and it never marks that company
  as seen, so tomorrow tries again.
- **It won't scrape anything it isn't allowed to.** People changing jobs is the
  single strongest early signal there is, and it's off the table because it means
  LinkedIn.

## Where it honestly stands

It runs end to end against live filings, on a schedule, and emails the result.
258 tests, none of which touch the network.

**The thesis is still a placeholder.** The criteria it currently judges against are
a reasonable guess and nothing more — healthcare AI and clinical software, with a
minimum raise size. Every number on this page was measured against criteria no
investor has looked at yet.

What belongs there is a real mandate. Stage, geography, cheque size, and above all
what rules a company out in the first thirty seconds. That comes from a conversation,
not from writing more code. It's one config file to change, and it's the change that
decides whether any of this is useful.

Known rough edges: only one domain is configured, and Slack delivery exists in
the code but has never been run.

---

Technical detail — architecture, running it, the schema, and what the real data
forced me to change — is in **[DEVELOPING.md](DEVELOPING.md)**.
