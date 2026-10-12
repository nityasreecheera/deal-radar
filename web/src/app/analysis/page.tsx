"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChartAsk } from "@/components/ChartAsk";

import {
  type Analysis,
  type DealSizes,
  type Market,
  type Meta,
} from "@/lib/api";

/**
 * The market, as the filings describe it.
 *
 * One breakdown per view, always by the reader's own criteria: across all
 * domains it splits by domain, inside one it splits by that thesis's "looking
 * for" lines. The global category vocabulary is deliberately absent — it fits
 * healthcare, which was written first, and draws distinctions about AI
 * infrastructure that nobody would ever make.
 *
 * Answers what nobody can work out by reading companies one a week, weeks
 * apart: what a normal raise looks like here, how early these companies are,
 * and how much of the round is usually gone by the time it surfaces.
 *
 * Strictly about the companies. The radar's own health — which SEC boxes earn
 * their keep, what the filter keeps rejecting — used to live at the bottom of
 * this page and does not any more. It is still on /api/analysis for whoever is
 * tuning the thing, but it was answering a question an analyst never asks.
 *
 * Deliberately tables and bars rather than charts. Every number here is one
 * someone will want to read exactly, and a number read exactly is a table.
 */
export default function AnalysisPage() {
  const [data, setData] = useState<Analysis | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [failed, setFailed] = useState(false);

  // Empty means every domain at once. Worth having as the default: the whole
  // point of a benchmark is a big enough sample, and splitting one domain into
  // two halves the numbers behind every figure on the page.
  const [domain, setDomain] = useState("");

  useEffect(() => {
    async function loadMeta() {
      try {
        const response = await fetch("/api/meta", { cache: "no-store" });

        if (response.ok) setMeta((await response.json()) as Meta);
      } catch {
        // The domain picker is a convenience; the page still works without it.
      }
    }

    void loadMeta();
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await fetch(
          `/api/analysis${domain ? `?theme=${encodeURIComponent(domain)}` : ""}`,
          { cache: "no-store" },
        );

        if (!response.ok) throw new Error(String(response.status));

        if (!cancelled) setData((await response.json()) as Analysis);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [domain]);

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

  // Typed rather than `?? {}`: an empty object literal widens to `{}` and
  // every field below it becomes an error.
  const domains = data.domains ?? [];
  const subdomains = data.subdomains ?? [];
  const market: Market = data.market ?? { companies: 0, excluded: 0 };
  const sizes: DealSizes = market.deal_sizes ?? { count: 0 };
  const ages = market.company_age ?? {};
  const ageBuckets = data.round_age ?? {};

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-[var(--color-rule)]">
        <div className="mx-auto max-w-4xl px-8 pt-8 pb-6">
          <BackLink />

          <h1 className="font-display mt-6 text-[1.75rem] leading-none tracking-tight">
            Analysis
          </h1>

          <div className="mt-3 flex flex-wrap items-end gap-x-6 gap-y-3">
            <label>
              <span className="label mb-1 block">Domain</span>
              <select
                value={domain}
                onChange={(event) => setDomain(event.target.value)}
                className="field pr-6"
              >
                <option value="">All domains</option>
                {(meta?.themes ?? []).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>

            <p className="text-[0.8125rem] text-[var(--color-ink-faint)]">
              <span className="tabular">{data.judged}</span> companies looked at
              {domain ? ` in ${domain}` : " across every domain"}.
            </p>
          </div>

          <p className="mt-3 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Every number on this page comes from decisions the filter made, not
            decisions you made — you haven&apos;t changed any of its verdicts
            yet.
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-4xl flex-1 space-y-12 px-8 py-10">
        {/* First, because a question asked is the reason someone opened the page. */}
        <ChartAsk />

        {/* Every domain at a glance. First, because "what am I even covering"
            comes before any number about one of them. */}
        {domains.length > 1 && !domain && (
          <section>
            <h2 className="font-display mb-1 text-[1.125rem]">
              Where the companies are
            </h2>
            <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
              How much there is to read in each domain, and what a raise looks
              like there.
            </p>

            <Table
              head={["domain", "worth reading", "typical raise", "range"]}
              keys={domains.map((row) => row.domain)}
              rows={domains.map((row) =>
                [
                  row.domain,
                  row.fitted ? (
                    <Link
                      key="n"
                      href={`/?theme=${encodeURIComponent(row.domain)}&verdict=fits`}
                      className="underline decoration-[var(--color-rule)] underline-offset-4 transition-colors hover:decoration-[var(--color-ink)]"
                    >
                      {row.fitted}
                    </Link>
                  ) : row.judged ? (
                    "none yet"
                  ) : (
                    "not run yet"
                  ),
                  money(row.typical_raise),
                  row.lower_quartile
                    ? `${money(row.lower_quartile)} – ${money(row.upper_quartile)}`
                    : "—",
                ] as React.ReactNode[],
              )}
              dim={domains.map((row) => !row.fitted)}
            />

            <p className="mt-3 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
              The counts are links — they open that domain&apos;s companies in
              the list, already filtered.
            </p>
          </section>
        )}
        {domain && subdomains.length > 0 && (
          <section>
            <h2 className="font-display mb-1 text-[1.125rem]">
              What kind of {domain} companies
            </h2>
            <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
              Split by the criteria&apos;s own &ldquo;looking for&rdquo; lines.
              {meta?.viewer === "owner" && (
                <>
                  {" "}Edit those on the{" "}
                  <Link href="/criteria" className="underline underline-offset-2">
                    criteria page
                  </Link>{" "}
                  and this splits differently.
                </>
              )}
            </p>

            <div className="max-w-2xl space-y-2">
              {subdomains.map((row) => {
                const line = String(
                  (row as Record<string, unknown>).subdomain ?? "",
                );
                const companies = Number(
                  (row as Record<string, unknown>).companies ?? 0,
                );
                const raised = Number(
                  (row as Record<string, unknown>).raised ?? 0,
                );
                const typical = Number(
                  (row as Record<string, unknown>).typical ?? 0,
                );
                const largest = Math.max(
                  ...subdomains.map((r) =>
                    Number((r as Record<string, unknown>).companies ?? 0),
                  ),
                  1,
                );

                return (
                  <div key={line} className="flex items-center gap-3 text-sm">
                    <span className="w-64 shrink-0 text-[var(--color-ink-soft)]">
                      {line}
                    </span>

                    <Bar fraction={companies / largest} />

                    <span className="tabular whitespace-nowrap text-[var(--color-ink-faint)]">
                      {companies}
                      {typical ? (
                        <span className="text-[var(--color-ink-soft)]">
                          {"  ·  typically "}
                          {money(typical)}
                        </span>
                      ) : null}
                      {raised > 0 && (
                        <span>
                          {"  ·  "}
                          {money(raised)} in total
                        </span>
                      )}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* The market, not the machine. What an analyst came here for. */}
        <section>
          <h2 className="font-display mb-1 text-[1.125rem]">
            How much money are these companies raising?
          </h2>
          <p className="mb-4 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Based on the{" "}
            <span className="tabular">{market.companies}</span> companies we
            could actually identify
            {domain ? ` in ${domain}` : ""}.
            {(market.excluded ?? 0) > 0 && (
              <>
                {" "}
                Another <span className="tabular">{market.excluded}</span> are
                left out — either nobody could tell what they do, or they turned
                out to be a different kind of business that the search picked up
                along the way. Counting those would throw the numbers off.
              </>
            )}
          </p>

          {sizes.median == null ? (
            <p className="max-w-2xl text-sm text-[var(--color-ink-faint)]">
              Not enough companies yet to give a useful figure
              {domain ? ` for ${domain}` : ""}. It takes at least eight that
              disclosed what they were raising, and there{" "}
              {sizes.count === 1 ? "is" : "are"}{" "}
              <span className="tabular">{sizes.count ?? 0}</span> so far.
              {domain && " Try All domains, or give this one a few weeks."}
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
 * A bar inside a track of its own.
 *
 * The track is fixed-width and cannot shrink; the fill is a percentage of the
 * track. Sizing a bar as a percentage of a flex row does not work — a flex item
 * is clamped to the space actually left over, so every value above roughly 60%
 * rendered at exactly the same length. Three different numbers, three identical
 * bars, and the chart quietly said they were equal.
 */
function Bar({ fraction }: { fraction: number }) {
  return (
    <span
      className="block h-[10px] w-[220px] shrink-0 bg-[var(--color-rule)]"
      aria-hidden
    >
      <span
        className="block h-full bg-[var(--color-ink)]"
        style={{ width: `${Math.max(fraction * 100, fraction > 0 ? 1.5 : 0)}%` }}
      />
    </span>
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
    <div className="space-y-2">
      {entries.map(([label, count]) => (
        <div key={label} className="flex items-center gap-4 text-sm">
          <span className="w-44 shrink-0 text-[var(--color-ink-soft)]">
            {label}
          </span>

          <Bar fraction={count / largest} />

          <span className="tabular text-[var(--color-ink-faint)]">{count}</span>
        </div>
      ))}
    </div>
  );
}

function Table({
  head,
  rows,
  keys,
  dim = [],
}: {
  head: string[];
  rows: React.ReactNode[][];
  keys: string[];
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
              key={keys[rowIndex]}
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
