"use client";

import { useState } from "react";

import {
  VERDICT_LABEL,
  filingUrl,
  formatAmount,
  formatLocation,
  isUnread,
  type Candidate,
} from "@/lib/api";

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
  onRead,
}: {
  candidate: Candidate;
  onRead: (accession: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [saving, setSaving] = useState(false);

  const unread = isUnread(candidate);

  // Optional in the generated schema because the Pydantic field has a
  // default_factory, though the API always sends it.
  const people = candidate.people ?? [];
  const filing = filingUrl(candidate);

  async function markRead() {
    if (!unread || saving) return;

    setSaving(true);

    const response = await fetch(
      `/api/candidates/${encodeURIComponent(candidate.accession)}/viewed`,
      { method: "POST" },
    );

    setSaving(false);

    if (response.ok) onRead(candidate.accession);
  }

  function toggle() {
    setExpanded((open) => !open);

    // Opening something is reading it. Marking on expand rather than on page
    // load means the unread count reflects attention, not delivery.
    void markRead();
  }

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
          unread ? ACCENT[candidate.verdict] : "bg-transparent"
        }`}
      />

      <button
        type="button"
        onClick={toggle}
        aria-expanded={expanded}
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
          </span>
        </span>

        <span
          className={`shrink-0 text-[0.6875rem] tracking-[0.08em] uppercase ${
            VERDICT_TEXT[candidate.verdict]
          }`}
        >
          {VERDICT_LABEL[candidate.verdict]}
        </span>
      </button>

      {expanded && (
        <div className="space-y-6 pr-1 pb-6 pl-5">
          {candidate.summary && (
            <p className="font-display max-w-2xl text-[1.0625rem] leading-relaxed text-[var(--color-ink)]">
              {candidate.summary}
            </p>
          )}

          <p className="max-w-2xl text-[0.9375rem] leading-relaxed text-[var(--color-ink-soft)]">
            {candidate.reason}
          </p>

          {candidate.website && (
            <a
              href={candidate.website}
              target="_blank"
              rel="noreferrer"
              className="inline-block border-b border-[var(--color-ink-faint)] pb-0.5 text-sm text-[var(--color-ink)] transition-colors hover:border-[var(--color-ink)]"
            >
              {candidate.website.replace(/^https?:\/\//, "")}
            </a>
          )}

          <section>
            <h3 className="label mb-2">Officers and directors</h3>

            {people.length === 0 ? (
              <p className="text-sm text-[var(--color-ink-faint)]">
                None named on the filing.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {people.map((person) => (
                  <li
                    key={`${person.first_name}-${person.last_name}`}
                    className="text-sm"
                  >
                    <span className="font-display text-[0.9375rem]">
                      {[person.first_name, person.last_name]
                        .filter(Boolean)
                        .join(" ")}
                    </span>
                    {(person.relationships ?? []).length > 0 && (
                      <span className="text-[var(--color-ink-soft)]">
                        {"  "}
                        {(person.relationships ?? []).join(", ")}
                      </span>
                    )}
                    {person.city && (
                      <span className="text-[var(--color-ink-faint)]">
                        {"  ·  "}
                        {person.city}
                        {person.state ? `, ${person.state}` : ""}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <dl className="grid max-w-2xl grid-cols-2 gap-x-10 gap-y-3 sm:grid-cols-3">
            <Fact label="Raising" value={formatAmount(candidate.offering_amount)} />
            <Fact label="Sold so far" value={formatAmount(candidate.amount_sold)} />
            <Fact
              label="Investors"
              value={
                candidate.investor_count == null
                  ? "unknown"
                  : String(candidate.investor_count)
              }
            />
            <Fact
              label="Incorporated"
              value={
                candidate.incorporated ? String(candidate.incorporated) : "unknown"
              }
            />
            <Fact label="Entity" value={candidate.entity_type ?? "unknown"} />
            <Fact label="Registered" value={candidate.jurisdiction ?? "unknown"} />
          </dl>

          {candidate.description && (
            <p className="max-w-2xl border-l border-[var(--color-rule)] pl-4 text-[0.8125rem] leading-relaxed text-[var(--color-ink-faint)] italic">
              {candidate.description}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-5 text-[0.75rem] text-[var(--color-ink-faint)]">
            {candidate.industry_group && <span>{candidate.industry_group}</span>}

            {filing && (
              <a
                href={filing}
                target="_blank"
                rel="noreferrer"
                className="border-b border-[var(--color-rule)] pb-0.5 transition-colors hover:border-[var(--color-ink-faint)] hover:text-[var(--color-ink-soft)]"
              >
                the SEC filing
              </a>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="tabular mt-0.5 text-sm text-[var(--color-ink)]">{value}</dd>
    </div>
  );
}
