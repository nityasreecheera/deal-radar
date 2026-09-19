"use client";

import { useState } from "react";

import { CriteriaList } from "@/components/CriteriaList";
import { LogoutButton } from "@/components/LogoutButton";
import { formatAmount } from "@/lib/api";

type Result = {
  company_name: string;
  verdict: string;
  reason: string;
  summary?: string | null;
  website?: string | null;
  offering_amount?: number | null;
  filed_date: string;
  city?: string | null;
  state?: string | null;
};

type Run = {
  considered: number;
  judged: number;
  results: Result[];
  problems: string[];
};

// Matches the cap the API enforces, so the limit is reached with an
// explanation in the box rather than a rejection after a round trip.
const MAX_CRITERIA = 8;

/**
 * Write your own criteria; see what the radar finds.
 *
 * This is the whole of what a guest sees. Not a reduced version of the list —
 * a different thing, because the list is a record of conclusions and those are
 * the strategy. Here the filings are the same public SEC data and the criteria
 * are yours, so nothing anyone else decided is on the page.
 */
export default function TryPage() {
  const [domain, setDomain] = useState("");
  const [include, setInclude] = useState<string[]>([]);
  const [exclude, setExclude] = useState<string[]>([]);

  // What is typed but not yet added. Pressing search has to count it: a line
  // sitting in the box is something the person has said they want, and
  // ignoring it makes the button look broken.
  const [includeDraft, setIncludeDraft] = useState("");
  const [excludeDraft, setExcludeDraft] = useState("");
  const [maxAmount, setMaxAmount] = useState("");

  const [run, setRun] = useState<Run | null>(null);
  const [running, setRunning] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  /** A list plus whatever is still in its box, without duplicates. */
  function withDraft(items: string[], draft: string): string[] {
    const line = draft.trim();

    return line && !items.includes(line) ? [...items, line] : items;
  }

  async function search() {
    const wanted = withDraft(include, includeDraft);
    const unwanted = withDraft(exclude, excludeDraft);

    if (wanted.length === 0) {
      setFailed("Type at least one thing to look for.");
      return;
    }

    // Show them as added, so the run and the page agree on what was asked.
    setInclude(wanted);
    setExclude(unwanted);
    setIncludeDraft("");
    setExcludeDraft("");

    setRunning(true);
    setFailed(null);
    setRun(null);

    try {
      const response = await fetch("/api/try", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain: domain.trim(),
          include: wanted,
          exclude: unwanted,
          max_amount: maxAmount ? Number(maxAmount) * 1_000_000 : null,
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);

        throw new Error(
          body?.detail?.errors?.[0] ?? `The run failed (${response.status}).`,
        );
      }

      setRun((await response.json()) as Run);
    } catch (error) {
      // A run that could not happen is said to have failed. Showing an empty
      // list would claim nothing matched, which nobody established.
      setFailed(error instanceof Error ? error.message : "The run failed.");
    } finally {
      setRunning(false);
    }
  }

  // Labels are plain sentences at a readable size rather than the tiny
  // letter-spaced capitals used on the owner's pages. Those work as filter
  // captions above a dense list; here they are the only instructions anyone
  // gets, and a caption you have to lean in to read is not an instruction.
  const label = "mb-2 block text-[0.9375rem] font-medium text-[var(--color-ink)]";
  const hint = "mb-2 block text-[0.8125rem] text-[var(--color-ink-faint)]";
  const box =
    "w-full rounded border border-[var(--color-rule)] bg-[var(--color-paper)] " +
    "px-3 py-2.5 text-[0.9375rem] text-[var(--color-ink)] " +
    "focus:border-[var(--color-ink)] focus:outline-none";

  return (
    <div className="mx-auto min-h-screen w-full max-w-2xl px-8 py-16">
      <header className="flex items-baseline justify-between">
        <h1 className="font-display text-[1.75rem] leading-none tracking-tight">
          Deal Radar
        </h1>
        <LogoutButton />
      </header>

      {/* Two lines. What the companies are, and what to do on this page.
          Anything more about how it works is answered by using it. */}
      <p className="mt-6 text-[1.0625rem] leading-relaxed text-[var(--color-ink)]">
        Companies that just raised money, from SEC filings — usually before
        anyone announces it.
      </p>

      <p className="mt-2 text-[1.0625rem] leading-relaxed text-[var(--color-ink-soft)]">
        Tell it what you are looking for.
      </p>

      <section className="mt-12 space-y-10">
        <div>
          <label className={label} htmlFor="domain">
            Domain
          </label>
          <span className={hint}>
            Optional — energy, fintech, healthcare. It names the run.
          </span>
          <input
            id="domain"
            value={domain}
            onChange={(event) => setDomain(event.target.value)}
            placeholder="Energy"
            maxLength={40}
            className={box}
          />
        </div>

        <CriteriaList
          label="What you are looking for"
          hint="Add them one at a time. Plain English is fine."
          placeholder="software that makes data centres cheaper to run"
          items={include}
          onChange={setInclude}
          draft={includeDraft}
          onDraftChange={setIncludeDraft}
          max={MAX_CRITERIA}
        />

        <CriteriaList
          label="What to leave out"
          hint="Optional."
          placeholder="consultancies"
          items={exclude}
          onChange={setExclude}
          draft={excludeDraft}
          onDraftChange={setExcludeDraft}
          max={MAX_CRITERIA}
        />

        <div>
          <label className={label} htmlFor="max">
            Biggest raise you would consider
          </label>
          <span className={hint}>In millions. Leave blank for any size.</span>
          <input
            id="max"
            value={maxAmount}
            onChange={(event) => setMaxAmount(event.target.value)}
            type="number"
            min="0"
            step="0.1"
            placeholder="any"
            className={`${box} tabular max-w-[10rem]`}
          />
        </div>

        <div className="border-t border-[var(--color-rule)] pt-8">
          <button
            type="button"
            onClick={search}
            disabled={running}
            className="w-full rounded border border-[var(--color-ink)] bg-[var(--color-ink)] px-4 py-3 text-[0.9375rem] text-[var(--color-paper)] transition-opacity hover:opacity-90 disabled:opacity-50 sm:w-auto sm:px-8"
          >
            {running ? "Reading filings…" : "Find companies"}
          </button>

          {/* Only the wait. How many companies get read is a real limit, but
              before a run it is a number with nothing to compare it to — the
              result says it afterwards, with the total beside it. */}
          <p className="mt-3 text-[0.8125rem] text-[var(--color-ink-faint)]">
            Takes about half a minute.
          </p>

          {failed && (
            <p className="mt-3 text-[0.9375rem] text-[var(--color-nofit)]">
              {failed}
            </p>
          )}
        </div>
      </section>

      {run && (
        <section className="mt-14 border-t border-[var(--color-rule)] pt-10">
          {/* A run where most companies could not be judged is not a run
              where they did not match. Saying "nothing matched" there would
              report a conclusion nobody reached — the mistake this project
              exists to avoid, and it would be reported to a stranger. */}
          <h2 className="text-[1.0625rem] font-medium">
            {run.results.length > 0
              ? `${run.results.length} worth a look`
              : run.judged === 0
                ? "Could not check"
                : run.problems.length > 0
                  ? "No matches among the ones I could read"
                  : "Nothing matched"}
            {domain.trim() && run.results.length > 0 && (
              <span className="text-[var(--color-ink-soft)]">
                {" "}
                in {domain.trim()}
              </span>
            )}
          </h2>

          <p className="mt-1 mb-8 text-[0.8125rem] text-[var(--color-ink-faint)]">
            {run.judged === 0 ? (
              <>
                None of the {run.problems.length} companies could be read, so
                nothing here has been ruled in or out.
              </>
            ) : (
              <>
                Of {run.considered} companies on file, the {run.judged} closest
                to what you asked for were read in full.
                {run.problems.length > 0 && (
                  <>
                    {" "}
                    Another {run.problems.length} could not be read.
                  </>
                )}
              </>
            )}
          </p>

          <div className="space-y-9">
            {run.results.map((result) => (
              <article
                key={result.company_name + result.filed_date}
                className="border-l-2 border-[var(--color-fits)] pl-4"
              >
                <h2 className="font-display text-[1.0625rem] leading-snug">
                  {result.company_name}
                </h2>

                <p className="mt-1 flex flex-wrap items-baseline gap-x-3 text-[0.75rem] text-[var(--color-ink-faint)]">
                  <span className="tabular">
                    {formatAmount(result.offering_amount)}
                  </span>
                  <span>·</span>
                  <span className="tabular">{result.filed_date}</span>
                  {result.city && (
                    <>
                      <span>·</span>
                      <span>
                        {result.city}
                        {result.state ? `, ${result.state}` : ""}
                      </span>
                    </>
                  )}
                  <span>·</span>
                  <span
                    className={
                      result.verdict === "fits"
                        ? "text-[var(--color-fits)]"
                        : "text-[var(--color-maybe)]"
                    }
                  >
                    {result.verdict === "fits" ? "fits" : "maybe"}
                  </span>
                </p>

                {result.summary && (
                  <p className="mt-2 text-[0.9375rem] leading-relaxed">
                    {result.summary}
                  </p>
                )}

                <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-[var(--color-ink-soft)]">
                  {result.reason}
                </p>

                {result.website && (
                  <a
                    href={result.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1.5 inline-block text-[0.75rem] text-[var(--color-ink-faint)] underline underline-offset-2"
                  >
                    {result.website.replace(/^https?:\/\//, "")}
                  </a>
                )}
              </article>
            ))}
          </div>

          {run.results.length === 0 && run.problems.length === 0 && (
            <p className="text-[0.9375rem] text-[var(--color-ink-soft)]">
              Nothing matched those criteria. Try a broader line — the pool is
              whatever has been filed and looked up so far, not all of EDGAR.
            </p>
          )}

          {run.judged === 0 && run.problems.length > 0 && (
            <p className="text-[0.9375rem] leading-relaxed text-[var(--color-maybe)]">
              Something is wrong at my end, not with your criteria. Please try
              again later.
            </p>
          )}

        </section>
      )}
    </div>
  );
}
