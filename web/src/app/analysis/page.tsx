"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  VERDICT_LABEL,
  effectiveVerdict,
  type Analysis,
  type DealSizes,
  type Market,
} from "@/lib/api";

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
  // Typed rather than `?? {}`: an empty object literal widens to `{}` and
  // every field below it becomes an error.
  const market: Market = data.market ?? { companies: 0 };
  const sizes: DealSizes = market.deal_sizes ?? { count: 0 };
  const ages = market.company_age ?? {};
  const ageBuckets = data.round_age ?? {};

  // Biggest first, so the categories worth benchmarking lead.
  const byCategory = Object.entries(market.by_category ?? {}).sort(
    (first, second) => (second[1].count ?? 0) - (first[1].count ?? 0),
  ) as [string, DealSizes][];

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
        {/* The market, not the machine. What an analyst came here for. */}
        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">
            What a raise looks like here
          </h2>
          <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Across{" "}
            <span className="tabular">{market.companies}</span> healthcare
            companies on record. Companies that turned out not to be healthcare
            are left out — a median that includes an animation studio is not a
            benchmark for this market.
          </p>

          {sizes.median == null ? (
            <p className="text-sm text-[var(--color-ink-faint)]">
              Not enough disclosed raises yet to say.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap gap-x-12 gap-y-4">
                <Figure label="Typical raise" value={money(sizes.median)} />
                <Figure
                  label="Middle half"
                  value={`${money(sizes.lower_quartile)} – ${money(sizes.upper_quartile)}`}
                />
                <Figure
                  label="Full range"
                  value={`${money(sizes.smallest)} – ${money(sizes.largest)}`}
                />
              </div>

              <p className="mt-3 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
                Half of everything raised in this space sits between{" "}
                {money(sizes.lower_quartile)} and {money(sizes.upper_quartile)}.
                A company asking for far more or far less than that is doing
                something worth asking about.
              </p>
            </>
          )}

          {byCategory.length > 0 && (
            <div className="mt-6">
              <h3 className="label mb-2">By what they do</h3>
              <Table
                head={["category", "companies", "typical", "middle half"]}
                rows={byCategory.map(([name, row]) => [
                  name,
                  String(row.count),
                  money(row.median),
                  `${money(row.lower_quartile)} – ${money(row.upper_quartile)}`,
                ])}
              />
              <p className="mt-2 text-[0.8125rem] text-[var(--color-ink-faint)]">
                Only categories with at least eight disclosed raises. Below that
                a median is a coincidence.
              </p>
            </div>
          )}
        </section>

        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">
            How young the companies are
          </h2>
          <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Years between incorporation and the filing. Stage, without anyone
            having to self-report it.
          </p>

          <Bars data={ages} />
        </section>

        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">Where they are</h2>

          <Bars
            data={Object.fromEntries(
              (market.locations ?? []).map((place) => [
                String((place as Record<string, unknown>).state),
                Number((place as Record<string, unknown>).companies),
              ]),
            )}
          />
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

          <Bars data={ageBuckets} />
        </section>

        <hr className="border-[var(--color-rule)]" />

        <div>
          <h2 className="font-display text-[1.125rem]">Tuning the radar</h2>
          <p className="mt-1 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Below here is about the tool rather than the market — what it is
            searching, what it keeps throwing away, and where you disagreed with
            it. Useful when deciding what to change in the thesis file.
          </p>
        </div>

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
                                  ? Math.max((260 * slice.seen) / source.seen, 3)
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

/** A raise, the way an analyst says it out loud. */
function money(amount: number | null | undefined): string {
  if (amount == null) return "—";

  if (amount >= 1_000_000) {
    return `$${(amount / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  }

  return `$${Math.round(amount / 1000)}k`;
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="label mb-1">{label}</p>
      <p className="font-display tabular text-[1.375rem] leading-none">
        {value}
      </p>
    </div>
  );
}

/**
 * Counts as bars. Proportional to the largest, not to the total — the question
 * is which is biggest, not what share each holds of a whole.
 */
function Bars({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data);
  const largest = Math.max(...entries.map(([, n]) => n), 1);

  if (entries.length === 0) {
    return (
      <p className="text-sm text-[var(--color-ink-faint)]">Nothing yet.</p>
    );
  }

  return (
    <div className="max-w-xl space-y-2">
      {entries.map(([label, count]) => (
        <div key={label} className="flex items-center gap-4 text-sm">
          <span className="w-44 shrink-0 text-[var(--color-ink-soft)]">
            {label}
          </span>

          <span
            className="h-[10px] bg-[var(--color-ink)]"
            style={{
              width: `${(100 * count) / largest}%`,
              minWidth: count ? "2px" : 0,
            }}
          />

          <span className="tabular text-[var(--color-ink-faint)]">{count}</span>
        </div>
      ))}
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
