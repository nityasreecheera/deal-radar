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
            <span className="tabular">{data.judged}</span> companies looked at
            so far. Every number on this page comes from decisions the filter
            made, not decisions you made — you haven&apos;t changed any of its
            verdicts yet.
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-4xl flex-1 space-y-12 px-8 py-10">
        {/* The market, not the machine. What an analyst came here for. */}
        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">
            How much money are these companies raising?
          </h2>
          <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Based on the{" "}
            <span className="tabular">{market.companies}</span> companies that
            actually turned out to be healthcare. The rest were things like
            animation software and banking apps — the search picks those up, and
            counting them here would throw the numbers off.
          </p>

          {sizes.median == null ? (
            <p className="text-sm text-[var(--color-ink-faint)]">
              Not enough disclosed raises yet to say.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap gap-x-12 gap-y-4">
                <Figure
                  label="Typical raise"
                  value={money(sizes.median)}
                  note="half raise more, half raise less"
                />
                <Figure
                  label="Most land between"
                  value={`${money(sizes.lower_quartile)} – ${money(sizes.upper_quartile)}`}
                  note="the middle half of all companies"
                />
                <Figure
                  label="Smallest and largest"
                  value={`${money(sizes.smallest)} – ${money(sizes.largest)}`}
                  note="the two extremes"
                />
              </div>

              <p className="mt-3 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
                <strong className="font-normal text-[var(--color-ink)]">
                  What to do with this:
                </strong>{" "}
                if a company turns up raising {money(sizes.median)}, that is
                completely normal here. One raising far more or far less than{" "}
                {money(sizes.lower_quartile)} to {money(sizes.upper_quartile)} is
                unusual, and worth asking why.
              </p>
            </>
          )}

          {byCategory.length > 0 && (
            <div className="mt-6">
              <h3 className="label mb-2">
                The same thing, split by type of company
              </h3>
              <Table
                head={[
                  "type of company",
                  "how many",
                  "typical raise",
                  "most land between",
                ]}
                rows={byCategory.map(([name, row]) => [
                  name,
                  String(row.count),
                  money(row.median),
                  `${money(row.lower_quartile)} – ${money(row.upper_quartile)}`,
                ])}
              />
              <p className="mt-2 text-[0.8125rem] text-[var(--color-ink-faint)]">
                Only shown for types with at least eight companies. With fewer
                than that, an average is just a coincidence.
              </p>
            </div>
          )}
        </section>

        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">
            How old are these companies?
          </h2>
          <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            The gap between when the company was legally created and when it
            filed to raise money. A rough guide to how early you are catching
            them.
          </p>

          <Bars data={ages} />
        </section>

        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">
            Which states are they in?
          </h2>

          <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            The state on the filing, which is usually where the company is based.
          </p>

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
            How far along was the raise before you heard about it?
          </h2>
          <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Companies have to tell the SEC when they first took money.
            Comparing that to the day they filed shows how long the raise had
            already been running. Under two weeks means you are seeing it early.
            Over a year usually means it is finished and there is nothing left to
            join.
          </p>

          <Bars data={ageBuckets} />
        </section>

        <hr className="border-[var(--color-rule)]" />

        <div>
          <h2 className="font-display text-[1.125rem]">
            About the tool, not the companies
          </h2>
          <p className="mt-1 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Everything above is about the companies. Everything below is about
            how the radar itself is doing — where it looks, what it keeps
            rejecting, and where you disagreed with it. Read this when you want
            to change what it searches for.
          </p>
        </div>

        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">
            Where the radar looks
          </h2>
          <p className="mb-6 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Every company ticks one industry box when it files. These are the
            boxes the radar searches. Underneath each one is what those companies
            turned out to be once we looked them up.
            <br />
            <br />
            This matters because the box is the only thing we know{" "}
            <em>before</em> spending money looking a company up. So it is the
            only place where a change actually saves anything.
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
            Boxes that have never produced a single useful company account for{" "}
            <span className="tabular">
              {sources
                .filter((source) => source.fitted === 0)
                .reduce((sum, source) => sum + source.seen, 0)}
            </span>{" "}
            companies downloaded, looked up and judged for nothing. Those are
            the boxes worth switching off.
          </p>
        </section>

        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">
            What kinds of company the radar finds
          </h2>
          <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Every company sorted by what it actually does. &quot;Fit&quot;
            means the filter thought it was worth putting in front of you. This
            is your own criteria described back to you — whatever has the most
            fits is what the radar is really hunting for.
          </p>

          <Table
            head={["type of company", "how many", "fit", "rejected"]}
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
            Companies where you disagreed with the filter
          </h2>
          <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            When you change a verdict yourself, it shows up here. This is the
            real test of whether the radar&apos;s criteria match what you
            actually want — a long list means the criteria need rewriting.
          </p>

          {overrides.length === 0 ? (
            <p className="text-sm text-[var(--color-ink-faint)]">
              Nothing here yet. Every verdict so far is the filter&apos;s own.
              Open any company and use <em>Your call</em> to change one.
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

function Figure({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div>
      <p className="label mb-1">{label}</p>
      <p className="font-display tabular text-[1.375rem] leading-none">
        {value}
      </p>
      {note && (
        <p className="mt-1 text-[0.75rem] text-[var(--color-ink-faint)]">
          {note}
        </p>
      )}
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
