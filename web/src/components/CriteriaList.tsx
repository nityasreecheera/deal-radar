"use client";

import { useState } from "react";

/**
 * Criteria entered one at a time.
 *
 * A textarea with "one per line" asks someone to hold a formatting rule in
 * their head while thinking about something else, and gives no sign whether
 * they got it right — a stray blank line or a trailing comma is invisible until
 * the results come back wrong. Adding one line at a time makes each criterion a
 * thing on the page that can be read back and removed.
 */
export function CriteriaList({
  label,
  hint,
  placeholder,
  items,
  onChange,
  max,
}: {
  label: string;
  hint?: string;
  placeholder: string;
  items: string[];
  onChange: (items: string[]) => void;
  max: number;
}) {
  const [draft, setDraft] = useState("");

  const full = items.length >= max;

  function add() {
    const line = draft.trim();

    // Silently ignoring a duplicate is better than adding it: the model would
    // be told the same thing twice and nothing would change except the reader's
    // confidence that the page is listening.
    if (!line || full || items.includes(line)) {
      setDraft("");
      return;
    }

    onChange([...items, line]);
    setDraft("");
  }

  return (
    <div>
      <span className="mb-2 block text-[0.9375rem] font-medium text-[var(--color-ink)]">
        {label}
      </span>

      {hint && (
        <span className="mb-2 block text-[0.8125rem] text-[var(--color-ink-faint)]">
          {hint}
        </span>
      )}

      {items.length > 0 && (
        <ul className="mb-3 space-y-2">
          {items.map((item) => (
            <li
              key={item}
              className="flex items-start justify-between gap-3 rounded border border-[var(--color-rule)] bg-[var(--color-paper-raised)] px-3 py-2"
            >
              <span className="text-[0.9375rem] leading-snug">{item}</span>

              <button
                type="button"
                onClick={() => onChange(items.filter((line) => line !== item))}
                aria-label={`Remove ${item}`}
                className="shrink-0 text-[0.8125rem] text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex gap-2">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // Enter adds. Inside a form it would submit instead, and on a page
            // whose only button runs a paid search that is the wrong default.
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
          placeholder={full ? `That is ${max}, the most it takes` : placeholder}
          disabled={full}
          className="w-full rounded border border-[var(--color-rule)] bg-[var(--color-paper)] px-3 py-2.5 text-[0.9375rem] text-[var(--color-ink)] focus:border-[var(--color-ink)] focus:outline-none disabled:opacity-50"
        />

        <button
          type="button"
          onClick={add}
          disabled={full || !draft.trim()}
          className="shrink-0 rounded border border-[var(--color-rule)] px-4 text-[0.9375rem] text-[var(--color-ink)] transition-colors hover:border-[var(--color-ink)] disabled:opacity-40"
        >
          Add
        </button>
      </div>
    </div>
  );
}
