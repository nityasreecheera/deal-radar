import { NextResponse, type NextRequest } from "next/server";

import {
  SESSION_COOKIE,
  matches,
  readSession,
  verifyToken,
} from "@/lib/session";

/**
 * The password gate. Renamed from middleware.ts — the middleware file
 * convention is deprecated in Next 16 and is now `proxy`.
 *
 * This exists because the site can be published through a tunnel, and two of its
 * endpoints are not harmless: /api/chat spends money on every request, and
 * /api/viewed writes. An ungated URL would let anyone holding it run up a bill
 * or mark the whole inbox read.
 *
 * Two ways in, on purpose:
 *
 *   A session cookie, for people. It can be cleared, which is what makes a
 *   logout button possible at all.
 *
 *   Basic auth, for scripts. curl and the deploy checks have no business with a
 *   login form, and this keeps every existing command working unchanged.
 *
 * Leave SHARE_USER and SHARE_PASSWORD unset for local development and nothing is
 * enforced.
 */
const USER = process.env.SHARE_USER;
const PASSWORD = process.env.SHARE_PASSWORD;

// Reachable without a session, or there would be no way to get one.
// /invite is open because it is how someone without the password gets a
// session at all. It grants nothing on its own: the token inside it is signed
// and dated, and the route refuses anything else.
const OPEN_PATHS = ["/login", "/auth/login", "/auth/logout", "/invite"];

/**
 * What a guest may reach.
 *
 * Everything else is the owner's working record, and the record is the strategy:
 * which companies were kept, which were passed on, and above all the reason
 * written beside each one. A visitor who can scroll that can reconstruct the
 * thesis in an afternoon, which is exactly what showing someone the tool is not
 * supposed to cost.
 *
 * So a guest gets the sandbox instead — their own criteria, run against the same
 * public filings — and nothing that says what anyone else concluded.
 */
const GUEST_PATHS = ["/try", "/api/try", "/api/health", "/auth/logout"];

function guestMayReach(pathname: string): boolean {
  return GUEST_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
}

function unauthorized() {
  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Deal Radar"' },
  });
}

function hasValidBasicAuth(request: NextRequest): boolean {
  const header = request.headers.get("authorization");

  if (!header?.startsWith("Basic ")) return false;

  let decoded: string;

  try {
    decoded = atob(header.slice("Basic ".length));
  } catch {
    return false;
  }

  const separator = decoded.indexOf(":");

  if (separator === -1) return false;

  return (
    matches(decoded.slice(0, separator), USER as string) &&
    matches(decoded.slice(separator + 1), PASSWORD as string)
  );
}

export async function proxy(request: NextRequest) {
  if (!USER || !PASSWORD) {
    return NextResponse.next();
  }

  const { pathname } = request.nextUrl;

  if (OPEN_PATHS.some((path) => pathname === path)) {
    return NextResponse.next();
  }

  const cookie = request.cookies.get(SESSION_COOKIE)?.value;

  // A bearer token first, because a program sends one on every request and has
  // no cookie to fall back on. Tokens are for other people's software; the
  // cookie is for a person in a browser.
  const authorization = request.headers.get("authorization");
  const bearer = authorization?.startsWith("Bearer ")
    ? authorization.slice("Bearer ".length).trim()
    : undefined;

  const role = bearer
    ? await verifyToken(bearer, PASSWORD)
    : await readSession(cookie, PASSWORD);

  if (bearer && role === null) {
    return new NextResponse("That token is not valid or has expired.", {
      status: 401,
    });
  }

  if (role === "reader") {
    // Read everything, change nothing. /api/chat is excluded with the writes
    // rather than the reads: it costs money on every call, and a token lives
    // inside somebody else's loop.
    const writes = request.method !== "GET" && request.method !== "HEAD";

    if (writes || pathname.startsWith("/api/chat")) {
      return new NextResponse("This token is read-only.", { status: 403 });
    }

    return NextResponse.next();
  }

  if (role === "guest") {
    if (guestMayReach(pathname)) {
      return NextResponse.next();
    }

    // An API call gets a status. A person gets sent to the page that is for
    // them, rather than a refusal for a page they did not know they were asking
    // for — following a link into the list should land somewhere useful.
    if (pathname.startsWith("/api/")) {
      return new NextResponse("Not available to guests.", { status: 403 });
    }

    return NextResponse.redirect(new URL("/try", request.url));
  }

  if (role === "owner") {
    return NextResponse.next();
  }

  if (hasValidBasicAuth(request)) {
    return NextResponse.next();
  }

  // An API call gets a status it can act on. A person gets the login form.
  //
  // The split matters beyond politeness: scripts/share.sh refuses to publish
  // until an unauthenticated request is rejected, and a redirect is not a
  // rejection it can distinguish from a working site.
  if (pathname.startsWith("/api/")) {
    return unauthorized();
  }

  const login = new URL("/login", request.url);

  // So logging in returns you where you were heading.
  if (pathname !== "/") {
    login.searchParams.set("next", pathname + request.nextUrl.search);
  }

  return NextResponse.redirect(login);
}

export const config = {
  // Everything but Next's own static assets, so the proxied API routes are
  // covered too — gating only the pages would leave the endpoints wide open.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
