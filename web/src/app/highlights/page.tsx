"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  VERDICT_LABEL,
  formatAmount,
  type Highlight,
  type HighlightList,
  type Verdict,
} from "@/lib/api";

/**
 * The week's highlights: companies already judged that filed again, and what
 * the new filing says.
 *
 * Rolling rather than a feed you scroll back through. Anything filed more than
 * seven days ago drops off, so the page is always "what moved this week" and
 * never an archive nobody reads. Strong signals first, then bigger rounds.
 *
 * A rejected company only appears on a strong signal. A new raise does not
 * change what a company does, but a round several times the size of the last
 * one is worth a second look even at something you passed on.
 */
export default function HighlightsPage() {
  const [data, setData] = useState<HighlightList | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await fetch("/api/highlights?days=7&limit=10", {
          cache: "no-store",
        });

        if (!response.ok) throw new Error(String(response.status));

        if (!cancelled) setData((await response.json()) as HighlightList);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-[var(--color-rule)]">
        <div className="mx-auto max-w-3xl px-8 pt-8 pb-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-[0.8125rem] text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
          >
            <span aria-hidden>←</span> All companies
          </Link>

          <h1 className="font-display mt-6 text-[1.75rem] leading-none tracking-tight">
            Highlights
          </h1>

          <p className="mt-3 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            Companies already judged that filed again in the last seven days,
            and what changed. The top ten, strongest first; older ones drop off
            on their own. A company marked no fit only shows up here on a strong
            signal.
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 px-8 py-8">
        {failed && (
          <p className="text-[0.875rem] text-[var(--color-ink-soft)]">
            Highlights could not be loaded. Try again in a minute.
          </p>
        )}

        {!failed && !data && <p className="label">Loading</p>}

        {data && data.highlights.length === 0 && (
          <p className="text-[0.875rem] text-[var(--color-ink-soft)]">
            Nothing this week. When a company you have already seen files
            again with a bigger round, a round that filled or new people on
            it, it shows up here.
          </p>
        )}

        {data && data.highlights.length > 0 && (
          <ol className="divide-y divide-[var(--color-rule)] border-y border-[var(--color-rule)]">
            {data.highlights.map((highlight) => (
              <Row key={highlight.accession} highlight={highlight} />
            ))}
          </ol>
        )}
      </main>
    </div>
  );
}

function Row({ highlight }: { highlight: Highlight }) {
  const verdict = highlight.verdict as Verdict;
  const theme = highlight.themes[0];
  const href =
    `/company/${encodeURIComponent(highlight.candidate_accession)}` +
    (theme ? `?theme=${encodeURIComponent(theme)}` : "");

  return (
    <li>
      <Link
        href={href}
        className="flex items-start gap-4 py-4 transition-colors hover:bg-[var(--color-paper-raised)]"
      >
        <span
          aria-hidden
          className={`mt-1 w-3 shrink-0 text-[0.75rem] ${
            highlight.strong
              ? "text-[var(--color-signal)]"
              : "text-[var(--color-ink-faint)]"
          }`}
        >
          {highlight.strong ? "▲" : "•"}
        </span>

        <span className="min-w-0 flex-1">
          <span className="font-display block text-[1.0625rem] leading-snug text-[var(--color-ink)]">
            {highlight.company_name}
            {highlight.strong && <span className="sr-only"> (strong signal)</span>}
          </span>

          <span className="mt-1 block text-[0.875rem] text-[var(--color-ink-soft)]">
            {highlight.headline}
          </span>

          <span className="mt-1 block text-[0.8125rem] text-[var(--color-ink-faint)]">
            <span className="tabular">{formatAmount(highlight.offering_amount)}</span>
            {"  ·  "}
            filed <span className="tabular">{highlight.filed_date}</span>
            {"  ·  "}
            was {VERDICT_LABEL[verdict] ?? highlight.verdict}
            {highlight.themes.length > 0 && <>{"  ·  "}{highlight.themes.join(", ")}</>}
          </span>
        </span>
      </Link>
    </li>
  );
}
