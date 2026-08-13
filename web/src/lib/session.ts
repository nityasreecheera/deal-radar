/**
 * A signed session cookie, so there is something to log out of.
 *
 * HTTP Basic auth has no logout. The browser caches the credentials for the
 * lifetime of the window and there is no standard way to ask it to forget them,
 * so a "log out" button on top of Basic auth is a button that does nothing.
 *
 * This is the smallest thing that gives a real one: a cookie holding an issue
 * time and an HMAC of that time, keyed on the share password. Nothing is stored
 * server-side — the signature is the whole check — and changing the password
 * invalidates every session already issued, which is the behaviour you want
 * from a password change.
 *
 * Basic auth still works alongside it, because scripts and `curl` have no
 * business with a login form.
 */

export const SESSION_COOKIE = "radar_session";

// Long enough not to be a daily nuisance on a tool someone opens each morning,
// short enough that a forgotten laptop stops working within a fortnight.
export const SESSION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60;

const encoder = new TextEncoder();

/** Compare without leaking length or position through timing. */
export function matches(given: string, expected: string): boolean {
  if (given.length !== expected.length) return false;

  let difference = 0;

  for (let index = 0; index < given.length; index += 1) {
    difference |= given.charCodeAt(index) ^ expected.charCodeAt(index);
  }

  return difference === 0;
}

function toBase64Url(bytes: ArrayBuffer): string {
  const binary = String.fromCharCode(...new Uint8Array(bytes));

  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function hmac(secret: string, payload: string): Promise<string> {
  // Web Crypto rather than node:crypto, so this works whichever runtime the
  // proxy ends up on.
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );

  return toBase64Url(await crypto.subtle.sign("HMAC", key, encoder.encode(payload)));
}

/** Mint a cookie value for a session starting now. */
export async function signSession(
  secret: string,
  issuedAt: number = Date.now(),
): Promise<string> {
  const payload = String(issuedAt);

  return `${payload}.${await hmac(secret, payload)}`;
}

/**
 * Whether a cookie was minted with this secret and has not expired.
 *
 * The expiry is checked here as well as on the cookie itself. A cookie's own
 * max-age is a request the browser is free to ignore, and anyone can send back
 * whatever they like.
 */
export async function verifySession(
  token: string | undefined,
  secret: string,
  now: number = Date.now(),
): Promise<boolean> {
  if (!token) return false;

  const separator = token.lastIndexOf(".");

  if (separator <= 0) return false;

  const payload = token.slice(0, separator);
  const signature = token.slice(separator + 1);

  const issuedAt = Number(payload);

  if (!Number.isFinite(issuedAt)) return false;

  const age = (now - issuedAt) / 1000;

  // A future issue date means a tampered or clock-skewed cookie. A little slack
  // for skew, then treat it as invalid.
  if (age < -60 || age > SESSION_MAX_AGE_SECONDS) return false;

  return matches(signature, await hmac(secret, payload));
}
