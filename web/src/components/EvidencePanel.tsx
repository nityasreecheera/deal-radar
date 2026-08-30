"use client";

import { type Detail } from "@/lib/api";

/**
 * What the filings say is true of a company, and what they say is not.
 *
 * Two lists, no total. A total needs weights, and any weighting of "raised
 * before" against "ten investors" is a judgement invented in this codebase
 * rather than read off a filing — invisible to whoever reads it and impossible
 * to argue with. An earlier version showed one and it was the least defensible
 * thing on the page.
 *
 * No probability either. That needs outcomes to calibrate against and this
 * project has none — no company on record has been acquired, failed or floated.
 */
export function EvidencePanel({ detail }: { detail: Detail }) {
  const signals = detail.assessment?.signals ?? [];

  if (signals.length === 0) return null;

  const favourable = signals.filter((s) => s.fired);
  const against = signals.filter((s) => !s.fired);

  return (
    <section>
      <h3 className="label mb-2">Signals</h3>

      <p className="mb-5 text-[0.75rem] text-[var(--color-ink-faint)]">
        What the filings show, not how likely they are to succeed.
      </p>

      {favourable.length > 0 && (
        <div className="mb-5">
          <p className="mb-2 text-[0.8125rem] font-medium text-[var(--color-fits)]">
            In its favour
          </p>

          <ul className="space-y-2.5">
            {favourable.map((signal) => (
              <li key={signal.name} className="text-sm">
                <span className="text-[var(--color-ink)]">{signal.name}</span>
                <span className="block text-[0.75rem] text-[var(--color-ink-soft)]">
                  {signal.detail}
                  {signal.means ? ` — ${signal.means}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {against.length > 0 && (
        <div>
          <p className="mb-2 text-[0.8125rem] font-medium text-[var(--color-ink-soft)]">
            Less in its favour
          </p>

          <ul className="space-y-2">
            {against.map((signal) => (
              <li key={signal.name} className="text-sm">
                <span className="text-[var(--color-ink-faint)]">
                  {signal.name}
                </span>
                <span className="block text-[0.75rem] text-[var(--color-ink-faint)]">
                  {signal.detail}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
