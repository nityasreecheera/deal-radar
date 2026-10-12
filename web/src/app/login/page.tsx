import { Suspense } from "react";

/**
 * The password form.
 *
 * A plain server-rendered form posting to /auth/login. No JavaScript needed, so
 * the browser's password manager treats it as a real login and offers to save
 * it — which is the practical reason anyone tolerates logging in at all.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string; invite?: string }>;
}) {
  const { next, error, invite } = await searchParams;

  return (
    <Suspense>
      <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-8">
        <h1 className="font-display text-[1.75rem] leading-none tracking-tight">
          Deal Radar
        </h1>

        {invite === "expired" && (
          <p className="mt-2 text-[0.8125rem] text-[var(--color-maybe)]">
            That invite link is no longer valid.
          </p>
        )}

        <form action="/auth/login" method="post" className="mt-8">
          <input type="hidden" name="next" value={next ?? "/"} />

          <label className="label mb-1 block" htmlFor="user">
            Name
          </label>

          <input
            id="user"
            name="user"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            className="field w-full"
          />

          <label className="label mt-4 mb-1 block" htmlFor="password">
            Password
          </label>

          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            className="field w-full"
          />

          {error && (
            <p className="mt-2 text-[0.8125rem] text-[var(--color-nofit)]">
              That is not right.
            </p>
          )}

          <button
            type="submit"
            className="mt-4 w-full rounded border border-[var(--color-ink)] bg-[var(--color-ink)] px-3 py-2 text-sm text-[var(--color-paper)] transition-opacity hover:opacity-90"
          >
            Sign in
          </button>
        </form>
      </main>
    </Suspense>
  );
}
