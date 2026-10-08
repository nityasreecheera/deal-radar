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

/**
 * Who a session belongs to.
 *
 * "owner" is a person signed in with the password or an invite link. "reader"
 * is someone else's program holding an API token.
 */
export type Role = "owner" | "reader";

/**
 * What an API token is allowed to do.
 *
 * "read" is for someone integrating against the judgements themselves — every
 * GET, no writes, and no /api/chat, because that one spends money on each call
 * and a token is meant to be left running in somebody else's program.
 */
export type Scope = "read";

const SCOPE_ROLE: Record<Scope, Role> = {
  read: "reader",
};

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

/**
 * Mint a cookie value for a session starting now.
 *
 * `expiresAt` pins the end explicitly, for a session that must not outlive
 * whatever granted it — an invite link, say. Without it the session runs the
 * usual fortnight. The two payload shapes are distinguishable and both are
 * signed, so an old cookie minted before this existed still verifies.
 */
export async function signSession(
  secret: string,
  issuedAt: number = Date.now(),
  expiresAt?: number,
): Promise<string> {
  const payload =
    expiresAt === undefined ? String(issuedAt) : `${issuedAt}:${expiresAt}`;

  return `${payload}.${await hmac(secret, payload)}`;
}

/**
 * Mint an API token for someone else's program.
 *
 * Carries its own name, scope and expiry, all inside the signature, so none of
 * the three can be edited by whoever holds it. The name is there for the
 * moment you need to ask which integration is making all the requests.
 *
 * Signed with the share password like everything else, so rotating that
 * revokes every token at once — a blunt instrument, but a real one, and the
 * only kind worth having when there is no token table to delete a row from.
 */
export async function signToken(
  secret: string,
  name: string,
  scope: Scope,
  expiresAt: number,
): Promise<string> {
  const payload = `token:${name}:${scope}:${expiresAt}`;

  return `${payload}.${await hmac(secret, payload)}`;
}

/** The role a bearer token carries, or null if it grants nothing. */
export async function verifyToken(
  token: string | undefined,
  secret: string,
  now: number = Date.now(),
): Promise<Role | null> {
  if (!token) return null;

  const separator = token.lastIndexOf(".");

  if (separator <= 0) return null;

  const payload = token.slice(0, separator);
  const signature = token.slice(separator + 1);
  const parts = payload.split(":");

  if (parts.length !== 4 || parts[0] !== "token") return null;

  const [, , scope, expires] = parts;
  const expiresAt = Number(expires);

  if (!Number.isFinite(expiresAt) || now > expiresAt) return null;

  const role = SCOPE_ROLE[scope as Scope];

  if (!role) return null;

  if (!matches(signature, await hmac(secret, payload))) return null;

  return role;
}

/**
 * Mint a link that grants access until a date, then stops.
 *
 * Signed with the same secret, so it is revocable the same way: changing the
 * share password kills every outstanding invite along with every session. The
 * expiry is inside the signed payload rather than alongside it, so it cannot be
 * edited by whoever holds the link.
 */
export async function signInvite(
  secret: string,
  expiresAt: number,
): Promise<string> {
  const payload = `invite:${expiresAt}`;

  return `${payload}.${await hmac(secret, payload)}`;
}

/** The moment an invite stops working, or null if it never did. */
export async function verifyInvite(
  token: string | undefined,
  secret: string,
  now: number = Date.now(),
): Promise<number | null> {
  if (!token) return null;

  const separator = token.lastIndexOf(".");

  if (separator <= 0) return null;

  const payload = token.slice(0, separator);
  const signature = token.slice(separator + 1);

  if (!payload.startsWith("invite:")) return null;

  const expiresAt = Number(payload.slice("invite:".length));

  if (!Number.isFinite(expiresAt) || now > expiresAt) return null;

  // Signature last: an expired link is refused whether or not it was genuine,
  // and checking the cheap condition first avoids the work.
  if (!matches(signature, await hmac(secret, payload))) return null;

  return expiresAt;
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
  return (await readSession(token, secret, now)) !== null;
}

/**
 * The role a cookie carries, or null if it is not valid.
 *
 * Separate from verifySession because the gate needs two different answers from
 * the same check: whether to let the request through at all, and whether to let
 * it write.
 */
export async function readSession(
  token: string | undefined,
  secret: string,
  now: number = Date.now(),
): Promise<Role | null> {
  if (!token) return null;

  const separator = token.lastIndexOf(".");

  if (separator <= 0) return null;

  const payload = token.slice(0, separator);
  const signature = token.slice(separator + 1);

  // Either "issuedAt" or "issuedAt:expiresAt". The second form ends when it
  // says rather than a fortnight after it began.
  const parts = payload.split(":");

  // A third part was a guest's marker. Guest access is gone, and a cookie
  // still carrying one must not be read as the owner's, so it grants nothing.
  if (parts.length > 2) return null;

  const [issued, expires] = parts;
  const issuedAt = Number(issued);

  if (!Number.isFinite(issuedAt)) return null;

  const age = (now - issuedAt) / 1000;

  // A future issue date means a tampered or clock-skewed cookie. A little slack
  // for skew, then treat it as invalid.
  if (age < -60) return null;

  if (expires === undefined) {
    if (age > SESSION_MAX_AGE_SECONDS) return null;
  } else {
    const expiresAt = Number(expires);

    if (!Number.isFinite(expiresAt) || now > expiresAt) return null;
  }

  if (!matches(signature, await hmac(secret, payload))) return null;

  return "owner";
}
