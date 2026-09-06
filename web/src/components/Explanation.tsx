"use client";

import { useEffect, useState } from "react";

type Explanation = {
  profile?: string | null;
  fallback?: string | null;
  unavailable?: string | null;
};

/**
 * What the company does, in prose.
 *
 * The scraped homepage text used to be printed here as it arrived — headings
 * with nothing under them, a truncation marker, the same phrase twice, and once
 * the name of a background graphic. It was the company's marketing shown raw,
 * which left the reading to whoever opened the page.
 *
 * The explanation is written on the first view and kept, so it arrives after the
 * rest of the page rather than with it. That is why this fetches separately: the
 * facts, the funding history and the verdict should not wait on a model call.
 */
export function Explanation({ accession }: { accession: string }) {
  const [state, setState] = useState<Explanation | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await fetch(
          `/api/candidates/${encodeURIComponent(accession)}/profile`,
          { cache: "no-store" },
        );

        if (!response.ok) throw new Error(String(response.status));

        if (!cancelled) setState((await response.json()) as Explanation);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [accession]);

  if (failed) return null;

  if (!state) {
    return <p className="label text-[var(--color-ink-faint)]">Reading their site…</p>;
  }

  if (state.profile) {
    return (
      <div className="max-w-2xl space-y-3">
        {state.profile
          .split(/\n\s*\n/)
          .filter(Boolean)
          .map((paragraph, index) => (
            <p
              key={index}
              className="text-[0.9375rem] leading-relaxed text-[var(--color-ink)]"
            >
              {paragraph}
            </p>
          ))}
      </div>
    );
  }

  if (state.fallback) {
    return (
      <div className="max-w-2xl">
        {/* Labelled as theirs. It is marketing and reads like it, and passing it
            off as a description would be claiming a reading nobody did. */}
        <p className="label mb-1.5 text-[var(--color-ink-faint)]">
          In their own words
        </p>
        <p className="border-l border-[var(--color-rule)] pl-4 text-[0.8125rem] leading-relaxed text-[var(--color-ink-faint)] italic">
          {state.fallback}
        </p>
      </div>
    );
  }

  return null;
}
