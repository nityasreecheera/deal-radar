"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { CompanyProfile } from "@/components/CompanyProfile";
import { ContactPanel } from "@/components/ContactPanel";
import { DecisionPanel } from "@/components/DecisionPanel";
import {
  VERDICT_LABEL,
  effectiveVerdict,
  formatAmount,
  formatLocation,
  isOverridden,
  type Candidate,
  type Detail,
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
  const [detail, setDetail] = useState<Detail | null>(null);
  const [missing, setMissing] = useState(false);

  const backTo = from ? `/?${decodeURIComponent(from)}` : "/";

  // The domain is already in the filters the list handed over. A verdict
  // belongs to a thesis, not to a company, so a page opened from a
  // domain-filtered list has to ask that domain — otherwise it shows whichever
  // thesis happened to run last, which for a company judged differently by two
  // of them is simply the wrong answer.
  const domain = from
    ? new URLSearchParams(decodeURIComponent(from)).get("theme")
    : null;

  const forDomain = domain ? `?theme=${encodeURIComponent(domain)}` : "";

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await fetch(
          `/api/candidates/${encodeURIComponent(accession)}${forDomain}`,
          { cache: "no-store" },
        );

        if (!response.ok) throw new Error(String(response.status));

        if (!cancelled) setCandidate((await response.json()) as Candidate);

        const extra = await fetch(
          `/api/candidates/${encodeURIComponent(accession)}/detail${forDomain}`,
          { cache: "no-store" },
        );

        // Detail is a bonus, not the page. A company still reads fine without
        // its funding history.
        if (extra.ok && !cancelled) setDetail((await extra.json()) as Detail);
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
  }, [accession, forDomain]);

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
            {candidate.theme && (
              <>
                <span className="text-[var(--color-rule)]">·</span>
                {/* A chip rather than another dotted fact. The domain is not
                    a property of the company like its size or address — it is
                    which set of criteria produced the verdict beside it, and
                    it should look like a different kind of thing. Neutral ink
                    on purpose: the verdict colours next to it are meaningful,
                    and a second colour here would compete with them. */}
                <span className="rounded-full border border-[var(--color-rule)] bg-[var(--color-paper-raised)] px-2 py-0.5 text-[0.75rem] font-medium text-[var(--color-ink)]">
                  {candidate.theme}
                </span>
              </>
            )}
          </p>
        </div>
      </header>

      {/* Evidence on the left, the decision on the right.

          Side by side rather than stacked because the two are read together:
          you are looking at the funding history *while* deciding, and a panel
          above the evidence gets scrolled past and forgotten. Sticky, so it
          stays reachable however far down the page you are.

          It stacks below the evidence on narrow screens, where there is no room
          for two columns and scrolling past a form to reach the facts would be
          worse than scrolling past the facts to reach the form. */}
      <main className="mx-auto w-full max-w-5xl flex-1 px-8 py-8">
        <div className="flex flex-col gap-10 lg:flex-row lg:items-start">
          <div className="min-w-0 flex-1">
            <CompanyProfile candidate={candidate} detail={detail} />
          </div>

          <aside className="w-full shrink-0 lg:sticky lg:top-8 lg:w-[19rem]">
            {/* A rule separates it from the evidence: a left edge beside the
                column, a top edge when it drops underneath. */}
            <div className="border-t border-[var(--color-rule)] pt-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6">
              <DecisionPanel candidate={candidate} onChange={setCandidate} />

              {detail && (
                <div className="mt-8">
                  <ContactPanel
                    candidate={candidate}
                    detail={detail}
                    onChange={setCandidate}
                  />
                </div>
              )}
            </div>
          </aside>
        </div>
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
