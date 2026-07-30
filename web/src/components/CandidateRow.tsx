"use client";

import { useState } from "react";

import {
  VERDICT_LABEL,
  VERDICT_MARK,
  badgeStyle,
  filingUrl,
  formatAmount,
  formatLocation,
  isUnread,
  rowStyle,
  type Candidate,
} from "@/lib/api";

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

    if (response.ok) {
      onRead(candidate.accession);
    }
  }

  function toggle() {
    setExpanded((open) => !open);

    // Opening something is reading it. Marking read on expand rather than on
    // page load means the unread count reflects attention, not delivery.
    void markRead();
  }

  return (
    <li className={`rounded-lg border px-4 py-3 transition-colors ${rowStyle(candidate)}`}>
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-start justify-between gap-4 text-left"
        aria-expanded={expanded}
      >
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2">
            {unread && (
              <span
                className="h-2 w-2 shrink-0 rounded-full bg-sky-500"
                aria-label="unread"
              />
            )}
            <span className={`font-medium ${unread ? "" : "font-normal"}`}>
              {candidate.company_name}
            </span>
          </span>

          <span className="mt-1 block text-xs">
            {formatAmount(candidate.offering_amount)} ·{" "}
            {formatLocation(candidate)} · filed {candidate.filed_date}
            {candidate.theme ? ` · ${candidate.theme}` : ""}
          </span>
        </span>

        <span
          className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${badgeStyle(
            candidate,
          )}`}
        >
          {VERDICT_MARK[candidate.verdict]} {VERDICT_LABEL[candidate.verdict]}
        </span>
      </button>

      {expanded && (
        <div className="mt-3 space-y-4 border-t border-current/10 pt-3 text-sm">
          <p>{candidate.reason}</p>

          {candidate.website && (
            <a
              href={candidate.website}
              target="_blank"
              rel="noreferrer"
              className="inline-block text-sm font-medium underline"
            >
              {candidate.website.replace(/^https?:\/\//, "")}
            </a>
          )}

          {candidate.description && (
            <p className="text-xs opacity-75">{candidate.description}</p>
          )}

          <Detail label="Officers and directors">
            {people.length === 0 ? (
              <span className="opacity-60">None named on the filing.</span>
            ) : (
              <ul className="space-y-0.5">
                {people.map((person) => (
                  <li key={`${person.first_name}-${person.last_name}`}>
                    <span className="font-medium">
                      {[person.first_name, person.last_name]
                        .filter(Boolean)
                        .join(" ")}
                    </span>
                    {(person.relationships ?? []).length > 0 && (
                      <span className="opacity-70">
                        {" — "}
                        {(person.relationships ?? []).join(", ")}
                      </span>
                    )}
                    {person.city && (
                      <span className="opacity-60">
                        {" · "}
                        {person.city}
                        {person.state ? `, ${person.state}` : ""}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Detail>

          <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
            <Fact label="Raising" value={formatAmount(candidate.offering_amount)} />
            <Fact label="Sold so far" value={formatAmount(candidate.amount_sold)} />
            <Fact
              label="Investors"
              value={
                candidate.investor_count === null ||
                candidate.investor_count === undefined
                  ? "unknown"
                  : String(candidate.investor_count)
              }
            />
            <Fact
              label="Incorporated"
              value={candidate.incorporated ? String(candidate.incorporated) : "unknown"}
            />
            <Fact label="Entity" value={candidate.entity_type ?? "unknown"} />
            <Fact label="Registered" value={candidate.jurisdiction ?? "unknown"} />
          </div>

          <div className="flex flex-wrap gap-3 text-xs opacity-70">
            {candidate.industry_group && (
              <span>SEC group: {candidate.industry_group}</span>
            )}

            {filing && (
              <a
                href={filing}
                target="_blank"
                rel="noreferrer"
                className="underline"
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

function Detail({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-1 text-xs uppercase tracking-wide opacity-60">{label}</p>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide opacity-60">{label}</p>
      <p className="text-sm">{value}</p>
    </div>
  );
}
