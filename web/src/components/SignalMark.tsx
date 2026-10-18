/**
 * The mark beside a verdict when a later filing says something strong: a much
 * bigger round, a round that filled, a jump in what has sold. The verdict was a
 * snapshot, and this says the snapshot may be out of date.
 *
 * A triangle rather than a colour alone, so it still reads in greyscale, and
 * the words go in the title and in text for screen readers.
 */
export function SignalMark({ alert }: { alert?: string | null }) {
  if (!alert) return null;

  return (
    <span
      title={`Positive signal: ${alert}`}
      className="shrink-0 text-[0.75rem] leading-none text-[var(--color-signal)]"
    >
      <span aria-hidden>▲</span>
      <span className="sr-only">Positive signal: {alert}</span>
    </span>
  );
}
