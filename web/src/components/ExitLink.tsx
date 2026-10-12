/**
 * Where the owner's "Sign out" would be, for a visitor: the way out.
 *
 * Back to the introduction, forgetting "Continue as guest". The owner signs in from
 * the introduction page, so a visitor's header carries only this.
 *
 * A plain link rather than <Link>: Next prefetches <Link> targets, and a prefetch
 * of /leave would forget the visitor's choice before they clicked.
 */
export function ExitLink() {
  return (
    <a
      href="/leave"
      className="text-[0.8125rem] text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
    >
      Exit
    </a>
  );
}
