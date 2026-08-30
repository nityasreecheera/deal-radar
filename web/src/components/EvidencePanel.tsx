"use client";

import { type Detail } from "@/lib/api";

/**
 * What the filings support, as a score you can take apart.
 *
 * Deliberately not a success probability. That needs outcomes to calibrate
 * against and this project has none — no company on record has been acquired,
 * failed or floated. A number claiming "73% likely to succeed" would be
 * invented and would look exactly as confident as a real one.
 *
 * So every signal is listed, fired or not, with the figure behind it. A reader
 * who disagrees with the score can see precisely which line they disagree with,
 * which is the difference between evidence and an opinion wearing a number.
 */
export function EvidencePanel({ detail }: { detail: Detail }) {
  const assessment = detail.assessment;
  const signals = assessment?.signals ?? [];

  if (signals.length === 0) return null;

  const score = assessment?.out_of_ten ?? 0;
  const fired = signals.filter((s) => s.fired);

  return (
    <section>
      <h3 className="label mb-2">Evidence</h3>

      <div className="mb-1 flex items-baseline gap-2">
        <span className="font-display tabular text-[1.75rem] leading-none">
          {score}
        </span>
        <span className="text-sm text-[var(--color-ink-faint)]">
          out of 10
        </span>
      </div>

      <p className="mb-4 text-[0.75rem] text-[var(--color-ink-faint)]">
        {fired.length} of {signals.length} signals present. This is how much we
        know, not how likely they are to succeed — nothing here predicts an
        outcome.
      </p>

      <ul className="space-y-2.5">
        {signals.map((signal) => (
          <li key={signal.name} className="flex gap-2.5 text-sm">
            <span
              aria-hidden
              className={
                "mt-[3px] h-2.5 w-2.5 shrink-0 rounded-full " +
                (signal.fired
                  ? "bg-[var(--color-fits)]"
                  : "border border-[var(--color-rule)]")
              }
            />

            <span className="min-w-0">
              <span
                className={
                  signal.fired
                    ? "text-[var(--color-ink)]"
                    : "text-[var(--color-ink-faint)]"
                }
              >
                {signal.name}
              </span>

              {signal.detail && (
                <span className="block text-[0.75rem] text-[var(--color-ink-faint)]">
                  {signal.detail}
                </span>
              )}

              {signal.fired && signal.means && (
                <span className="block text-[0.75rem] text-[var(--color-ink-soft)]">
                  {signal.means}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
