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

  return (
    <div className="mx-auto min-h-screen w-full max-w-3xl px-8 py-10">
      <header className="border-b border-[var(--color-rule)] pb-6">
        <div className="flex items-baseline justify-between">
          <h1 className="font-display text-[1.75rem] leading-none tracking-tight">
            Deal Radar
          </h1>
          <LogoutButton />
        </div>

        <p className="mt-3 max-w-xl text-[0.9375rem] leading-relaxed text-[var(--color-ink-soft)]">
          Every weekday this reads new SEC Form D filings — companies that have
          just raised money, usually before any announcement — works out what
          each one actually does, and judges it against written criteria.
        </p>

        <p className="mt-2 max-w-xl text-[0.8125rem] leading-relaxed text-[var(--color-ink-faint)]">
          Write your own criteria below and it will run against the same
          filings. The judgements from my own theses are not shown.
        </p>
      </header>

      <section className="space-y-5 border-b border-[var(--color-rule)] py-6">
        <label className="block">
          <span className="label mb-1 block">Call it something</span>
          <input
            value={domain}
            onChange={(event) => setDomain(event.target.value)}
            placeholder="Data centre infrastructure"
            maxLength={40}
            className="field w-full"
          />
        </label>

        <label className="block">
          <span className="label mb-1 block">
            What you are looking for — one per line
          </span>
          <textarea
            value={include}
            onChange={(event) => setInclude(event.target.value)}
            rows={4}
            className="field w-full resize-y font-[inherit]"
          />
        </label>

        <label className="block">
          <span className="label mb-1 block">
            What rules a company out — one per line, optional
          </span>
          <textarea
            value={exclude}
            onChange={(event) => setExclude(event.target.value)}
            rows={2}
            placeholder="consultancies&#10;real estate"
            className="field w-full resize-y font-[inherit]"
          />
        </label>

        <div className="flex flex-wrap items-end gap-6">
          <label>
            <span className="label mb-1 block">Raising no more than ($M)</span>
            <input
              value={maxAmount}
              onChange={(event) => setMaxAmount(event.target.value)}
              type="number"
              min="0"
              step="0.1"
              placeholder="any"
              className="field tabular w-32"
            />
          </label>

          <button
            type="button"
            onClick={search}
            disabled={running}
            className="rounded border border-[var(--color-ink)] bg-[var(--color-ink)] px-4 py-2 text-sm text-[var(--color-paper)] transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {running ? "Reading filings…" : "Run it"}
          </button>
        </div>

        {failed && (
          <p className="text-[0.8125rem] text-[var(--color-nofit)]">{failed}</p>
        )}
      </section>

      {run && (
        <section className="py-6">
          <p className="label mb-5">
            Judged {run.judged} of {run.considered} companies ·{" "}
            {run.results.length} worth a look
          </p>

          <div className="space-y-6">
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
