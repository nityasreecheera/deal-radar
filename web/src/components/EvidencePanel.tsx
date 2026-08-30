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
 * Split into what is true and what is not, under headings that say so. The
 * first version distinguished them with a coloured dot alone, and "Round nearly
 * or fully sold / 12% sold" then read as a pass — the label said one thing, the
 * number underneath said the opposite, and only the dot resolved it.
 */
export function EvidencePanel({ detail }: { detail: Detail }) {
  const assessment = detail.assessment;
  const signals = assessment?.signals ?? [];

  if (signals.length === 0) return null;

  // The literal points, not the rescaled ten. Signals carry different
  // weights and the number available depends on what is knowable about this
  // company, so a rescaled score had neither a real numerator nor a real
  // denominator — "5 out of 10" was 5 of nothing you could point at.
  const points = assessment?.points ?? 0;
  const possible = assessment?.possible ?? 0;

  const present = signals.filter((s) => s.fired);
  const absent = signals.filter((s) => !s.fired);

  return (
    <section>
      <h3 className="label mb-2">Evidence</h3>

      <div className="mb-1 flex items-baseline gap-1.5">
        <span className="font-display tabular text-[1.75rem] leading-none">
          {points}
        </span>
        <span className="text-sm text-[var(--color-ink-faint)]">
          of {possible} points
        </span>
      </div>

      <p className="mb-1 text-[0.8125rem] text-[var(--color-ink-soft)]">
        {present.length} of {signals.length} things we look for are true.
      </p>

      <p className="mb-5 text-[0.75rem] text-[var(--color-ink-faint)]">
        Signals are worth 1 to 3 points depending on how much they tell you.
        A company with no filing history is scored out of fewer, rather than
        marked down for facts nobody has. This is how much we know about them,
        not how likely they are to succeed.
      </p>

      {present.length > 0 && (
        <div className="mb-5">
          <p className="mb-2 text-[0.8125rem] font-medium text-[var(--color-fits)]">
            In its favour
          </p>

          <ul className="space-y-2.5">
            {present.map((signal) => (
              <li key={signal.name} className="text-sm">
                <span className="text-[var(--color-ink)]">{signal.name}</span>
                <span className="tabular text-[var(--color-fits)]">
                  {" +"}
                  {signal.weight}
                </span>
                {signal.detail && (
                  <span className="block text-[0.75rem] text-[var(--color-ink-soft)]">
                    {signal.detail}
                    {signal.means ? ` — ${signal.means}` : ""}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {absent.length > 0 && (
        <div>
          <p className="mb-2 text-[0.8125rem] font-medium text-[var(--color-ink-faint)]">
            Not the case
          </p>

          <ul className="space-y-2">
            {absent.map((signal) => (
              <li key={signal.name} className="text-sm">
                <span className="text-[var(--color-ink-faint)]">
                  {signal.name}
                </span>
                <span className="tabular text-[var(--color-ink-faint)]">
                  {" "}
                  ({signal.weight})
                </span>
                {signal.detail && (
                  <span className="block text-[0.75rem] text-[var(--color-ink-faint)]">
                    {signal.detail}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
