/**
 * Sign out.
 *
 * A form rather than a link, because Next prefetches links and a logout
 * triggered by a prefetch would be a genuinely baffling bug.
 */
export function LogoutButton() {
  return (
    <form action="/auth/logout" method="post" className="inline">
      <button
        type="submit"
        className="text-[0.8125rem] text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
      >
        Sign out
      </button>
    </form>
  );
}
