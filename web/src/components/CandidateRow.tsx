"use client";

import Link from "next/link";

import {
  VERDICT_LABEL,
  effectiveVerdict,
  formatAmount,
  formatLocation,
  isUnread,
  type Candidate,
} from "@/lib/api";

/**
 * One line in the list. A link now, not an expander.
 *
 * Scanning and deciding are different jobs. The row does the first: name, size,
 * where, when, verdict — enough to know whether to look. Everything else lives
 * on the company's own page.
 *
 * `from` carries the list's current filters so the page can send you back to
 * the list you were actually looking at.
 */

/**
 * Verdict as a thin left rule rather than a tinted card.
 *
 * A washed background on every row makes the page shout; a two-pixel edge says
 * the same thing and leaves the text on paper where it is easiest to read.
 */
const ACCENT: Record<string, string> = {
  fits: "bg-[var(--color-fits)]",
  maybe: "bg-[var(--color-maybe)]",
  // Unknown gets no accent. It is not a judgement, so it should not read as one.
  unknown: "bg-[var(--color-rule)]",
  no_fit: "bg-[var(--color-nofit)]",
};

const VERDICT_TEXT: Record<string, string> = {
  fits: "text-[var(--color-fits)]",
  maybe: "text-[var(--color-maybe)]",
  unknown: "text-[var(--color-ink-faint)]",
  no_fit: "text-[var(--color-ink-faint)]",
};

export function CandidateRow({
  candidate,
  from,
  onRead,
}: {
  candidate: Candidate;
  from: string;
  onRead: (accession: string) => void;
}) {
  const unread = isUnread(candidate);
  const verdict = effectiveVerdict(candidate);

  const href =
    `/company/${encodeURIComponent(candidate.accession)}` +
    (from ? `?from=${encodeURIComponent(from)}` : "");

  return (
    <li
      className={`group relative border-b border-[var(--color-rule)] transition-opacity ${
        unread ? "" : "opacity-55"
      }`}
    >
      {/* The accent only appears while unread — once read, the row recedes. */}
      <span
        aria-hidden
        className={`absolute top-0 bottom-0 left-0 w-[2px] ${
          unread ? ACCENT[verdict] : "bg-transparent"
        }`}
      />

      <Link
        href={href}
        // Grey it immediately rather than waiting for the page to load and the
        // list to refetch. The page marks it read for real.
        onClick={() => onRead(candidate.accession)}
        className="flex w-full items-baseline gap-4 py-4 pr-1 pl-5 text-left transition-colors hover:bg-[var(--color-paper-raised)]"
      >
        <span className="min-w-0 flex-1">
          <span
            className={`font-display text-[1.0625rem] leading-snug ${
              unread ? "text-[var(--color-ink)]" : "text-[var(--color-ink-soft)]"
            }`}
          >
            {candidate.company_name}
          </span>

          <span className="mt-1 block text-[0.8125rem] text-[var(--color-ink-faint)]">
            <span className="tabular">
              {formatAmount(candidate.offering_amount)}
            </span>
            {"  ·  "}
            {formatLocation(candidate)}
            {"  ·  "}
            <span className="tabular">{candidate.filed_date}</span>
            {candidate.user_note && (
              <>
                {"  ·  "}
                <span className="text-[var(--color-ink-soft)]">noted</span>
              </>
            )}
          </span>
        </span>

        <span
          className={`shrink-0 text-[0.6875rem] tracking-[0.08em] uppercase ${VERDICT_TEXT[verdict]}`}
        >
          {VERDICT_LABEL[verdict]}
        </span>
      </Link>
    </li>
  );
}
