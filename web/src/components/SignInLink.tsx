import Link from "next/link";

/** Where a visitor's "Sign out" would be: the way in, for the owner. */
export function SignInLink() {
  return (
    <Link
      href="/login"
      className="text-[0.8125rem] text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
    >
      Owner sign in
    </Link>
  );
}
