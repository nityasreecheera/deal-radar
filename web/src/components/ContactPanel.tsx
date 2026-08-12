"use client";

import { useState } from "react";

import { type Candidate, type Detail } from "@/lib/api";

/**
 * Writing to a company, and remembering that you did.
 *
 * The compose button opens Gmail with the address filled in. "Find in Gmail"
 * opens a Gmail search for the company's domain, which is the honest answer to
 * "did I already email them and what did they say" — it points the browser at a
 * search you could have typed, rather than pretending to have read your mailbox.
 *
 * Actually syncing threads means the Gmail API and an OAuth flow. That is a much
 * larger thing to own, and it would be the first part of this project that holds
 * a credential able to read someone's mail.
 *
 * The status is set by hand and says so. Nothing here is inferred.
 */

const STATUSES: { value: string; label: string }[] = [
  { value: "emailed", label: "Emailed" },
  { value: "replied", label: "Replied" },
  { value: "meeting", label: "Meeting" },
  { value: "passed", label: "Passed" },
];

export function ContactPanel({
  candidate,
  detail,
  onChange,
}: {
  candidate: Candidate;
  detail: Detail;
  onChange: (updated: Candidate) => void;
}) {
  const [saving, setSaving] = useState(false);

  const email = candidate.contact_email;
  const status = candidate.outreach_status;

  async function setStatus(next: string) {
    setSaving(true);

    try {
      const response = await fetch(
        `/api/candidates/${encodeURIComponent(candidate.accession)}/outreach`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          // Clicking the current status clears it, so a misclick is undoable.
          body: JSON.stringify({ status: status === next ? "" : next }),
        },
      );

      if (response.ok) onChange((await response.json()) as Candidate);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section>
      <h3 className="label mb-2">Contact</h3>

      {email ? (
        <>
          <p className="mb-2 text-sm break-all text-[var(--color-ink-soft)]">
            {email}
          </p>

          <a
            href={detail.compose_url ?? "#"}
            target="_blank"
            rel="noreferrer"
            className="mb-2 inline-block rounded border border-[var(--color-ink)] px-3 py-1 text-sm text-[var(--color-ink)] transition-colors hover:bg-[var(--color-ink)] hover:text-[var(--color-paper)]"
          >
            Email in Gmail
          </a>
        </>
      ) : (
        <p className="mb-2 text-sm text-[var(--color-ink-faint)]">
          No address found on their site.
          {candidate.website && " Try the site directly."}
        </p>
      )}

      {detail.gmail_search_url && (
        <a
          href={detail.gmail_search_url}
          target="_blank"
          rel="noreferrer"
          className="block text-[0.8125rem] text-[var(--color-ink-faint)] underline-offset-2 transition-colors hover:text-[var(--color-ink)] hover:underline"
        >
          Find this company in Gmail
        </a>
      )}

      <div className="mt-4 flex flex-wrap gap-1.5">
        {STATUSES.map((choice) => {
          const active = status === choice.value;

          return (
            <button
              key={choice.value}
              type="button"
              disabled={saving}
              onClick={() => void setStatus(choice.value)}
              aria-pressed={active}
              className={
                "rounded-full border px-2.5 py-0.5 text-[0.8125rem] transition-colors disabled:opacity-50 " +
                (active
                  ? "border-[var(--color-ink)] bg-[var(--color-ink)] text-[var(--color-paper)]"
                  : "border-[var(--color-rule)] text-[var(--color-ink-faint)] hover:border-[var(--color-ink-soft)]")
              }
            >
              {choice.label}
            </button>
          );
        })}
      </div>

      <p className="mt-2 text-[0.75rem] text-[var(--color-ink-faint)]">
        {candidate.outreach_at
          ? `You marked this ${status} on ${candidate.outreach_at.slice(0, 10)}.`
          : "Set by hand — nothing here is read from your mailbox."}
      </p>
    </section>
  );
}
