"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { VERDICT_LABEL, effectiveVerdict, type Analysis } from "@/lib/api";

/**
 * The whole collection at once, rather than one company at a time.
 *
 * The list answers "what arrived today". This answers "what am I actually
 * seeing, and is the thesis right" — a question nobody can answer by reading
 * companies one a week, weeks apart.
 *
 * Deliberately tables and bars rather than charts. Every number here is a count
 * an analyst will want to read exactly, and a count read exactly is a table.
 */
export default function AnalysisPage() {
  const [data, setData] = useState<Analysis | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch("/api/analysis", { cache: "no-store" });

        if (!response.ok) throw new Error(String(response.status));

        setData((await response.json()) as Analysis);
      } catch {
        setFailed(true);
      }
    }

    void load();
  }, []);

  if (failed) {
    return (
      <main className="mx-auto max-w-3xl px-8 py-24">
        <BackLink />
        <p className="mt-8 text-sm text-[var(--color-ink-soft)]">
          Could not load the analysis.
        </p>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="mx-auto max-w-4xl px-8 py-10">
        <BackLink />
        <p className="label mt-8">Loading</p>
      </main>
    );
  }

  const categories = data.categories ?? [];
  const sources = data.sources ?? [];
  const overrides = data.overrides ?? [];
  const ages = data.round_age ?? {};

  const ageTotal = Object.values(ages).reduce((sum, n) => sum + n, 0);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-[var(--color-rule)]">
        <div className="mx-auto max-w-4xl px-8 pt-8 pb-6">
          <BackLink />

          <h1 className="font-display mt-6 text-[1.75rem] leading-none tracking-tight">
            Analysis
          </h1>

          <p className="mt-2 text-[0.8125rem] text-[var(--color-ink-faint)]">
            <span className="tabular">{data.judged}</span> companies judged.
            Everything here describes what the filter decided, not what you did
            — until you start overruling it.
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-4xl flex-1 space-y-12 px-8 py-10">
        {/* First, because it is the only table you can act on for free. */}
        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">
            Where companies come from
          </h2>
          <p className="mb-6 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            When a company files, it ticks one industry box. These are the boxes
            the radar searches, and underneath each one is what those companies
            actually turned out to be. This is the only thing known before a
            company costs anything to look up, so it is the only place a change
            saves money.
          </p>

          <div className="space-y-7">
            {sources.map((source) => {
              const slices = source.breakdown ?? [];
              const worthless = source.fitted === 0;

              return (
                <div key={source.industry_group}>
                  <div className="flex items-baseline justify-between gap-4 border-b border-[var(--color-rule)] pb-1">
                    <h3
                      className={`font-display text-[1rem] ${
                        worthless ? "text-[var(--color-ink-faint)]" : ""
                      }`}
                    >
                      {source.industry_group}
                    </h3>

                    <p className="text-[0.8125rem] text-[var(--color-ink-faint)]">
                      <span className="tabular">{source.seen}</span> companies
                      {source.fitted > 0 ? (
                        <>
                          {" · "}
                          <span className="tabular text-[var(--color-fits)]">
                            {source.fitted}
                          </span>{" "}
                          worth showing
                        </>
                      ) : (
                        <span> · nothing worth showing</span>
                      )}
                    </p>
                  </div>

                  {slices.length === 0 ? (
                    <p className="pt-2 text-sm text-[var(--color-ink-faint)]">
                      Searched, but nothing has ever been filed under it.
                    </p>
                  ) : (
                    <ul className="pt-2">
                      {slices.map((slice) => (
                        <li
                          key={slice.category}
                          className="flex items-center gap-3 py-[3px] text-sm"
                        >
                          <span className="w-52 shrink-0 text-[var(--color-ink-soft)]">
                            {slice.category}
                          </span>

                          <span
                            className={`h-[9px] ${
                              slice.fitted
                                ? "bg-[var(--color-fits)]"
                                : "bg-[var(--color-rule)]"
                            }`}
                            style={{
                              width: `${
                                source.seen
                                  ? Math.max(
                                      (260 * slice.seen) / source.seen,
                                      3,
                                    )
                                  : 0
                              }px`,
                            }}
                          />

                          <span className="tabular text-[var(--color-ink-faint)]">
                            {slice.seen}
                            {slice.fitted > 0 && (
                              <span className="text-[var(--color-fits)]">
                                {"  "}
                                {slice.fitted} fit
                              </span>
                            )}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>

          <p className="mt-6 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Boxes with nothing worth showing account for{" "}
            <span className="tabular">
              {sources
                .filter((source) => source.fitted === 0)
                .reduce((sum, source) => sum + source.seen, 0)}
            </span>{" "}
            companies fetched, looked up and judged. Those are the lines you
            could delete from the thesis file.
          </p>

        </section>

        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">
            What they turn out to be
          </h2>
          <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Known only after each company was looked up. Useful for reading the
            thesis back to yourself: the categories with a high hit rate are what
            it is actually selecting for.
          </p>

          <Table
            head={["category", "seen", "fit", "passed"]}
            rows={categories.map((row) => [
              row.category,
              String(row.seen),
              row.fitted ? String(row.fitted) : "—",
              row.rejected ? String(row.rejected) : "—",
            ])}
            dim={categories.map((row) => row.fitted === 0)}
          />

          {data.clusters && (
            <p className="mt-4 max-w-2xl border-l-2 border-[var(--color-rule)] pl-4 text-sm text-[var(--color-ink-soft)]">
              {data.clusters}
            </p>
          )}
        </section>

        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">
            How old rounds are when they reach you
          </h2>
          <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Measured from the first sale to the filing date. A round already
            running for months is not one you are early to, and it arrives
            looking exactly like one that opened last week.
          </p>

          <div className="max-w-xl space-y-2">
            {Object.entries(ages).map(([label, count]) => (
              <div key={label} className="flex items-center gap-4 text-sm">
                <span className="w-44 shrink-0 text-[var(--color-ink-soft)]">
                  {label}
                </span>

                <span
                  className="h-[10px] bg-[var(--color-ink)]"
                  style={{
                    width: `${ageTotal ? (100 * count) / ageTotal : 0}%`,
                    minWidth: count ? "2px" : 0,
                  }}
                />

                <span className="tabular text-[var(--color-ink-faint)]">
                  {count}
                </span>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">
            Where you overruled the filter
          </h2>
          <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            The honest measure of whether the thesis is right. A long list means
            the criteria do not say what you mean, which is a config problem
            rather than a model one.
          </p>

          {overrides.length === 0 ? (
            <p className="text-sm text-[var(--color-ink-faint)]">
              Nothing yet — every verdict on record is the filter&apos;s. Open a
              company and use <em>Your call</em> to disagree with one.
            </p>
          ) : (
            <ul className="space-y-2">
              {overrides.map((candidate) => (
                <li key={candidate.accession} className="text-sm">
                  <Link
                    href={`/company/${encodeURIComponent(candidate.accession)}`}
                    className="font-display text-[0.9375rem] hover:underline"
                  >
                    {candidate.company_name}
                  </Link>
                  <span className="text-[var(--color-ink-faint)]">
                    {" — filter said "}
                    {VERDICT_LABEL[candidate.verdict]}
                    {", you said "}
                    {VERDICT_LABEL[effectiveVerdict(candidate)]}
                  </span>
                  {candidate.user_note && (
                    <span className="block text-[var(--color-ink-soft)]">
                      “{candidate.user_note}”
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}

function Table({
  head,
  rows,
  dim = [],
}: {
  head: string[];
  rows: string[][];
  dim?: boolean[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full max-w-2xl border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--color-rule)]">
            {head.map((cell, index) => (
              <th
                key={cell}
                className={`label pb-2 font-normal ${
                  index === 0 ? "text-left" : "text-right"
                }`}
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={row[0]}
              className={`border-b border-[var(--color-rule)] ${
                // A row that has never produced a fit is the thing you might
                // switch off, so it recedes rather than shouts.
                dim[rowIndex] ? "text-[var(--color-ink-faint)]" : ""
              }`}
            >
              {row.map((cell, index) => (
                <td
                  key={index}
                  className={`py-2 ${
                    index === 0 ? "text-left" : "tabular text-right"
                  }`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/"
      className="inline-flex items-center gap-2 text-[0.8125rem] text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
    >
      <span aria-hidden>←</span> All companies
    </Link>
  );
}
