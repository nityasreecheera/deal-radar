"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { CompanyProfile } from "@/components/CompanyProfile";
import { DecisionPanel } from "@/components/DecisionPanel";
import {
  VERDICT_LABEL,
  effectiveVerdict,
  formatAmount,
  formatLocation,
  isOverridden,
  type Candidate,
} from "@/lib/api";

/**
 * One company, on its own page.
 *
 * A page rather than an expanding row because deciding on a company is a
 * different act from scanning a list — it wants the whole screen, a URL you can
 * send someone, and somewhere to come back from.
 *
 * The back link carries the list's filters in `from`, so returning lands on the
 * list as it was rather than on the default view. Losing someone's date range
 * because they opened a company would make the list feel disposable.
 */
export default function CompanyPage({
  params,
  searchParams,
}: {
  params: Promise<{ accession: string }>;
  searchParams: Promise<{ from?: string }>;
}) {
  const { accession } = use(params);
  const { from } = use(searchParams);

  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [missing, setMissing] = useState(false);

  const backTo = from ? `/?${decodeURIComponent(from)}` : "/";

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await fetch(
          `/api/candidates/${encodeURIComponent(accession)}`,
          { cache: "no-store" },
        );

        if (!response.ok) throw new Error(String(response.status));

        if (!cancelled) setCandidate((await response.json()) as Candidate);
      } catch {
        if (!cancelled) setMissing(true);
      }
    }

    // Opening a company is reading it. Marking here rather than on the list row
    // means arriving by direct link counts too, and the write is idempotent —
    // the first reading is the one kept.
    void fetch(`/api/candidates/${encodeURIComponent(accession)}/viewed`, {
      method: "POST",
    });

    void load();

    return () => {
      cancelled = true;
    };
  }, [accession]);

  if (missing) {
    return (
      <main className="mx-auto max-w-3xl px-8 py-24">
        <BackLink href={backTo} />
        <h2 className="font-display mt-8 text-xl">No such company</h2>
        <p className="mt-3 text-sm text-[var(--color-ink-soft)]">
          Nothing on record for {accession}.
        </p>
      </main>
    );
  }

  if (!candidate) {
    return (
      <main className="mx-auto max-w-3xl px-8 py-10">
        <BackLink href={backTo} />
        <p className="label mt-8">Loading</p>
      </main>
    );
  }

  const verdict = effectiveVerdict(candidate);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-[var(--color-rule)]">
        <div className="mx-auto max-w-3xl px-8 pt-8 pb-6">
          <BackLink href={backTo} />

          <h1 className="font-display mt-6 text-[1.75rem] leading-tight tracking-tight">
            {candidate.company_name}
          </h1>

          <p className="mt-2 flex flex-wrap items-baseline gap-x-3 text-[0.8125rem] text-[var(--color-ink-faint)]">
            <span className="tabular">
              {formatAmount(candidate.offering_amount)}
            </span>
            <span className="text-[var(--color-rule)]">·</span>
            <span>{formatLocation(candidate)}</span>
            <span className="text-[var(--color-rule)]">·</span>
            <span className="tabular">{candidate.filed_date}</span>
            <span className="text-[var(--color-rule)]">·</span>
            <span
              className={
                verdict === "fits"
                  ? "text-[var(--color-fits)]"
                  : verdict === "maybe"
                    ? "text-[var(--color-maybe)]"
                    : "text-[var(--color-ink-faint)]"
              }
            >
              {VERDICT_LABEL[verdict]}
            </span>
            {isOverridden(candidate) && (
              <span className="text-[var(--color-ink-soft)]">(your call)</span>
            )}
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 space-y-8 px-8 py-8">
        <DecisionPanel candidate={candidate} onChange={setCandidate} />

        <CompanyProfile candidate={candidate} />
      </main>
    </div>
  );
}

function BackLink({ href }: { href: string }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-2 text-[0.8125rem] text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
    >
      <span aria-hidden>←</span> All companies
    </Link>
  );
}
