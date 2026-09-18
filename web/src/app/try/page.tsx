"use client";

import { useState } from "react";

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

const EXAMPLE = [
  "software that makes data centres cheaper to run",
  "battery storage and grid hardware",
];

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
  const [include, setInclude] = useState(EXAMPLE.join("\n"));
  const [exclude, setExclude] = useState("");
  const [maxAmount, setMaxAmount] = useState("");

  const [run, setRun] = useState<Run | null>(null);
  const [running, setRunning] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const lines = (text: string) =>
    text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);

  async function search() {
    const criteria = lines(include);

    if (!domain.trim() || criteria.length === 0) {
      setFailed("Give it a name and at least one line of criteria.");
      return;
    }

    setRunning(true);
    setFailed(null);
    setRun(null);

    try {
      const response = await fetch("/api/try", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain: domain.trim(),
          include: criteria,
          exclude: lines(exclude),
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
            Name your search
          </label>
          <input
            id="domain"
            value={domain}
            onChange={(event) => setDomain(event.target.value)}
            placeholder="Data centre infrastructure"
            maxLength={40}
            className={box}
          />
        </div>

        <div>
          <label className={label} htmlFor="include">
            What you are looking for
          </label>
          <span className={hint}>One per line. Plain English is fine.</span>
          <textarea
            id="include"
            value={include}
            onChange={(event) => setInclude(event.target.value)}
            rows={4}
            className={`${box} resize-y font-[inherit] leading-relaxed`}
          />
        </div>

        <div>
          <label className={label} htmlFor="exclude">
            What to leave out
          </label>
          <span className={hint}>Optional.</span>
          <textarea
            id="exclude"
            value={exclude}
            onChange={(event) => setExclude(event.target.value)}
            rows={2}
            placeholder="consultancies&#10;real estate"
            className={`${box} resize-y font-[inherit] leading-relaxed`}
          />
        </div>

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

          <p className="mt-3 text-[0.8125rem] text-[var(--color-ink-faint)]">
            Takes about half a minute. It reads a dozen companies each time.
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
          <h2 className="text-[1.0625rem] font-medium">
            {run.results.length === 0
              ? "Nothing matched"
              : `${run.results.length} worth a look`}
          </h2>

          <p className="mt-1 mb-8 text-[0.8125rem] text-[var(--color-ink-faint)]">
            Read {run.judged} companies out of {run.considered} on file.
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

          {/* Said plainly. A run where companies failed to be judged is not a
              run where they did not match. */}
          {run.problems.length > 0 && (
            <p className="mt-6 text-[0.8125rem] text-[var(--color-maybe)]">
              {run.problems.length}{" "}
              {run.problems.length === 1 ? "company" : "companies"} could not be
              judged, so this is not a complete answer.
            </p>
          )}
        </section>
      )}
    </div>
  );
}
