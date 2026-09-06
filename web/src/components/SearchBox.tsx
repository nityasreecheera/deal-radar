"use client";

import { useEffect, useRef, useState } from "react";

/** How long to wait after the last keystroke before searching. */
const SETTLE_MS = 300;

/**
 * Free-text search over what has already been judged.
 *
 * Typed text lives here rather than in the URL. The URL is the source of truth
 * for every filter on this page, but rewriting it on each keystroke would fire a
 * request per character and fill the history with half-typed words — so the box
 * holds the text and hands it over once typing stops.
 *
 * `value` still flows back in, because the URL can change without this box: the
 * back button, a shared link, or clearing the filters. When it does, the box
 * follows it.
 */
export function SearchBox({
  value,
  reading,
  unsupported,
  onCommit,
}: {
  value: string;
  reading: string[];
  unsupported: string[];
  onCommit: (query: string) => void;
}) {
  const [text, setText] = useState(value);

  // Keep the latest callback without making it a dependency of the timer: it is
  // a new function on every render, and depending on it would reset the wait on
  // every render rather than on every keystroke.
  const commit = useRef(onCommit);
  commit.current = onCommit;

  useEffect(() => setText(value), [value]);

  useEffect(() => {
    if (text === value) return;

    const timer = setTimeout(() => commit.current(text.trim()), SETTLE_MS);

    return () => clearTimeout(timer);
  }, [text, value]);

  return (
    <div className="relative pb-5">
      <label>
        <span className="label mb-1 block">Search</span>

        <input
          type="search"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            // Enter searches now rather than waiting out the timer, and Escape
            // clears — both are what a search box is expected to do.
            if (event.key === "Enter") commit.current(text.trim());
            if (event.key === "Escape") setText("");
          }}
          placeholder="Try: pre-seed AI infra companies under $1M about cooling"
          aria-label="Search judged companies"
          className="field w-full"
        />
      </label>

      {/* What the sentence was taken to mean. Shown whenever anything beyond
          plain words was recognised, because a search that quietly reinterprets
          the question is worse than one that ignores it — and because seeing
          "under $3M" is how you find out which convention "pre-seed" used. */}
      {reading.length > 0 && (
        <p className="mt-2 text-[0.8125rem] text-[var(--color-ink-soft)]">
          <span className="label mr-2">Reading as</span>
          {reading.join(" · ")}
        </p>
      )}

      {/* The part of the question that could not be honoured. Naming it is the
          point: returning a confident list that silently ignores half of what
          was asked is the failure this project keeps finding. */}
      {unsupported.length > 0 && (
        <p className="mt-1.5 text-[0.8125rem] text-[var(--color-maybe)]">
          Not applied — {unsupported.join("; ")}.
        </p>
      )}

      {/* Said once, next to the box, because it is the difference between this
          and a search engine: it only covers companies already judged. */}
      <p className="mt-1.5 text-[0.75rem] text-[var(--color-ink-faint)]">
        Searches companies this radar has already judged — not the web, and not
        all of EDGAR.
      </p>
    </div>
  );
}
