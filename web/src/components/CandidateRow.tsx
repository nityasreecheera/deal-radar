"use client";

import { useState } from "react";

import {
  VERDICT_LABEL,
  VERDICT_MARK,
  badgeStyle,
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
        <div className="mt-3 border-t border-current/10 pt-3 text-sm">
          <p>{candidate.reason}</p>

          {candidate.description && (
            <p className="mt-2 text-xs opacity-75">{candidate.description}</p>
          )}

          <div className="mt-2 flex flex-wrap gap-3 text-xs">
            {candidate.website && (
              <a
                href={candidate.website}
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                {candidate.website.replace(/^https?:\/\//, "")}
              </a>
            )}

            {candidate.industry_group && <span>{candidate.industry_group}</span>}

            {candidate.incorporated && (
              <span>incorporated {candidate.incorporated}</span>
            )}
          </div>
        </div>
      )}
    </li>
  );
}
