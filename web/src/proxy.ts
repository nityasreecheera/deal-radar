import { NextResponse, type NextRequest } from "next/server";

import {
  SESSION_COOKIE,
  matches,
  readSession,
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

  const role = await readSession(cookie, PASSWORD);

  if (role === "guest") {
    // A guest is shown the tool, not given it. Reading is the whole point;
    // writing would let a visitor overwrite judgements that took months to
    // accumulate, and /api/chat spends money on every call.
    const writes = request.method !== "GET" && request.method !== "HEAD";
    const costs = request.nextUrl.pathname.startsWith("/api/chat");

    if (writes || costs) {
      return new NextResponse(
        "This is a read-only guest session.",
        { status: 403 },
      );
    }

    return NextResponse.next();
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
