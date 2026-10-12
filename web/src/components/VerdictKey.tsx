/**
 * What the four verdicts mean, in one place, for anyone reading the list.
 *
 * Worded the way the README defines them, because the distinction between
 * "maybe" and "unknown" is the one people get wrong: a maybe is a company we
 * understand whose fit is arguable; an unknown is one we could not find out
 * about at all.
 */
const VERDICTS: { label: string; mark: string; tone: string; meaning: string }[] = [
  {
    label: "Fits",
    mark: "✓",
    tone: "text-[var(--color-fits)]",
    meaning: "Clearly within the criteria.",
  },
  {
    label: "Maybe",
    mark: "~",
    tone: "text-[var(--color-maybe)]",
    meaning: "We know what the company does; whether it fits is arguable.",
  },
  {
    label: "Unknown",
    mark: "?",
    tone: "text-[var(--color-ink-faint)]",
    meaning: "We couldn't find out what the company does.",
  },
  {
    label: "No fit",
    mark: "✗",
    tone: "text-[var(--color-nofit)]",
    meaning: "Clearly outside the criteria.",
  },
];

export function VerdictKey() {
  return (
    <details className="text-[0.75rem] text-[var(--color-ink-soft)]">
      <summary className="cursor-pointer text-[var(--color-ink-faint)] hover:text-[var(--color-ink)]">
        What the verdicts mean
      </summary>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        {VERDICTS.map((verdict) => (
          <div key={verdict.label} className="contents">
            <dt className={verdict.tone}>
              {verdict.mark} {verdict.label}
            </dt>
            <dd>{verdict.meaning}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
