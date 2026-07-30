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

Early. This README is the design, written before most of the code, deliberately.

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
