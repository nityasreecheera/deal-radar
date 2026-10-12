import Link from "next/link";

/**
 * Where a first-time visitor lands.
 *
 * The site used to open on a password form, which told a visitor nothing except
 * that they were not welcome. Now it says what the radar is in a few lines and
 * lets them in to read. Signing in is still here, small, for the one person who
 * changes things.
 */
export default function WelcomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-8 py-16">
      <h1 className="font-display text-[2.25rem] leading-none tracking-tight">
        Deal Radar
      </h1>

      <p className="mt-5 text-[1.0625rem] leading-relaxed text-[var(--color-ink)]">
        Companies that have just filed to raise money with the SEC, read and
        judged against an investment thesis — often before anyone announces the
        round.
      </p>

      <ul className="mt-6 space-y-2 text-[0.9375rem] leading-relaxed text-[var(--color-ink-soft)]">
        <li>Every weekday, new Form D filings are pulled from the SEC.</li>
        <li>Each company is looked up, then judged: fits, maybe, no fit, or unknown.</li>
        <li>Every verdict comes with its reason and the filing behind it.</li>
      </ul>

      <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-3">
        <a
          href="/start"
          className="rounded border border-[var(--color-ink)] bg-[var(--color-ink)] px-5 py-2.5 text-sm text-[var(--color-paper)] transition-opacity hover:opacity-90"
        >
          Get started
        </a>

        <Link
          href="/login"
          className="text-[0.8125rem] text-[var(--color-ink-faint)] underline underline-offset-2 transition-colors hover:text-[var(--color-ink)]"
        >
          Owner sign in
        </Link>
      </div>

      <p className="mt-10 text-[0.75rem] text-[var(--color-ink-faint)]">
        Read-only for visitors. Built from public SEC filings.
      </p>
    </main>
  );
}
