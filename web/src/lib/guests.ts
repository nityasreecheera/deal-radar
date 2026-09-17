import type { Role } from "@/lib/session";

/**
 * Named guests who can sign in with a name and no password.
 *
 * For showing the tool to someone — a reviewer, an interviewer — where a link
 * full of signed token is awkward to put in an email and a shared password is
 * something you can never take back. "Sign in as leonisguest" is a sentence.
 *
 * Be clear about what this is: a guest name is a password that is short,
 * memorable and meant to be typed by a stranger. It is guessable, so it buys
 * convenience rather than security, and everything that makes it safe to hand
 * out is somewhere else — every guest expires, guests cannot write, and the
 * entry can be deleted at any time.
 *
 * Configured as GUEST_LOGINS in the environment, one entry per guest:
 *
 *   GUEST_LOGINS="leonisguest=2026-09-24,acmeguest=2026-10-01"
 *
 * The date is the last day the name works, read as UTC midnight at its end.
 */
export type Guest = {
  name: string;
  expiresAt: number;
};

export function parseGuests(raw: string | undefined): Guest[] {
  if (!raw) return [];

  return raw
    .split(",")
    .map((entry) => {
      const [name, date] = entry.split("=").map((part) => part?.trim());

      if (!name || !date) return null;

      // End of that day rather than its start, so a guest given "until the
      // 24th" has the 24th.
      const expiresAt = Date.parse(`${date}T23:59:59Z`);

      return Number.isFinite(expiresAt) ? { name: name.toLowerCase(), expiresAt } : null;
    })
    .filter((guest): guest is Guest => guest !== null);
}

/**
 * The guest by that name, if the name is known and the date has not passed.
 *
 * An expired guest is indistinguishable from an unknown one to whoever is
 * typing: both are simply refused. Saying "that guest has expired" would confirm
 * the name was real, which is the one thing worth not confirming about a
 * credential you can guess at.
 */
export function findGuest(
  name: string,
  raw: string | undefined = process.env.GUEST_LOGINS,
  now: number = Date.now(),
): Guest | null {
  const wanted = name.trim().toLowerCase();

  if (!wanted) return null;

  return (
    parseGuests(raw).find(
      (guest) => guest.name === wanted && now <= guest.expiresAt,
    ) ?? null
  );
}

export const GUEST_ROLE: Role = "guest";
