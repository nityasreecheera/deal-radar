import { NextResponse, type NextRequest } from "next/server";

import {
  SESSION_COOKIE,
  matches,
  readSession,
  verifyToken,
} from "@/lib/session";

/**
 * The gate. Renamed from middleware.ts — the middleware file convention is
 * deprecated in Next 16 and is now `proxy`.
 *
 * The site is public to read and private to change. Anyone may browse the
 * judgements; only the owner writes, spends money, or sees the strategy.
 *
 * Three kinds of visitor:
 *
 *   The owner, with a session cookie (people) or Basic auth (scripts and the
 *   deploy checks, which have no business with a login form).
 *
 *   A reader: someone else's program holding a signed API token. Every GET, no
 *   writes, no /api/chat.
 *
 *   Everyone else: public. GET only, and not the endpoints that show the
 *   strategy rather than the findings. The API filters what they read — see
 *   src/visibility.py — and refuses the same endpoints again, so a mistake here
 *   is not a hole.
 *
 * Who is asking is sent to the API as a header on every request. It is always
 * set here, overwriting anything the client sent, because the API trusts it.
 *
 * Leave SHARE_USER and SHARE_PASSWORD unset for local development and everyone
 * is the owner.
 */
const USER = process.env.SHARE_USER;
const PASSWORD = process.env.SHARE_PASSWORD;

const VIEWER_HEADER = "x-radar-viewer";

// An anonymous id per browser, so the domains a visitor writes come back to them
// and nobody else. Random, never tied to a person, and separate from the
// "Continue as guest" cookie so Exit does not throw a visitor's domains away.
const VISITOR_ID_HEADER = "x-radar-visitor-id";
const VISITOR_ID_COOKIE = "radar_vid";
const ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

// Set by the landing page's "Continue as guest", so a returning visitor goes straight
// to the companies instead of the introduction each time.
const VISITOR_COOKIE = "radar_visitor";

type Viewer = "owner" | "reader" | "public";

// Reachable by anyone, or there would be no way in.
// /invite grants nothing on its own: the token inside it is signed and dated.
const OPEN_PATHS = [
  "/login",
  "/auth/login",
  "/auth/logout",
  "/invite",
  "/welcome",
  "/start",
  "/leave",
];

// What a visitor may not read even though it is a GET: the owner's criteria are
// the strategy, the digests and disagreements are the owner's working record,
// and the runs are spending.
const OWNER_API_PATHS = [
  "/api/digests",
  "/api/disagreements",
  "/api/runs",
];

// Below /api/theses, everything is the owner's: previews and runs spend money.
// /api/theses itself is readable — the API returns a visitor only the public
// domains, as examples.
const OWNER_API_PREFIXES = ["/api/theses/"];

// The only writes a visitor may make: their own domains. The API keys these by
// the visitor's id and keeps them out of the owner's record entirely.
const VISITOR_WRITES = ["/api/visitor", "/api/charts"];

const OWNER_PAGES: string[] = [];

function startsWith(pathname: string, paths: string[]): boolean {
  return paths.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

/**
 * Pass the request on, telling the API who is asking.
 *
 * Both headers are always set or removed here, never passed through from the
 * client: the API trusts them.
 */
function onward(request: NextRequest, viewer: Viewer) {
  const headers = new Headers(request.headers);

  headers.set(VIEWER_HEADER, viewer);
  headers.delete(VISITOR_ID_HEADER);

  if (viewer !== "public") {
    return NextResponse.next({ request: { headers } });
  }

  // A visitor keeps the id they have, or is given one on this request.
  const existing = request.cookies.get(VISITOR_ID_COOKIE)?.value;
  const id = existing && ID_PATTERN.test(existing) ? existing : crypto.randomUUID();

  headers.set(VISITOR_ID_HEADER, id);

  const response = NextResponse.next({ request: { headers } });

  if (id !== existing) {
    response.cookies.set(VISITOR_ID_COOKIE, id, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      maxAge: 365 * 24 * 60 * 60,
      secure: request.nextUrl.protocol === "https:",
    });
  }

  return response;
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
    return onward(request, "owner");
  }

  const { pathname } = request.nextUrl;
  const isApi = pathname.startsWith("/api/");

  if (OPEN_PATHS.some((path) => pathname === path)) {
    return onward(request, "public");
  }

  // A bearer token first, because a program sends one on every request and has
  // no cookie to fall back on.
  const authorization = request.headers.get("authorization");
  const bearer = authorization?.startsWith("Bearer ")
    ? authorization.slice("Bearer ".length).trim()
    : undefined;

  const role = bearer
    ? await verifyToken(bearer, PASSWORD)
    : await readSession(request.cookies.get(SESSION_COOKIE)?.value, PASSWORD);

  if (bearer && role === null) {
    return new NextResponse("That token is not valid or has expired.", {
      status: 401,
    });
  }

  if (role === "reader") {
    // Read everything, change nothing. /api/chat is excluded with the writes:
    // it costs money on every call, and a token lives in somebody else's loop.
    const writes = request.method !== "GET" && request.method !== "HEAD";

    if (writes || pathname.startsWith("/api/chat")) {
      return new NextResponse("This token is read-only.", { status: 403 });
    }

    return onward(request, "reader");
  }

  if (role === "owner" || hasValidBasicAuth(request)) {
    return onward(request, "owner");
  }

  // Everyone else reads, and only reads.
  const reads = request.method === "GET" || request.method === "HEAD";

  if (isApi) {
    if (!reads && startsWith(pathname, VISITOR_WRITES)) {
      return onward(request, "public");
    }

    if (!reads) {
      // 401 rather than 403: signing in would make this work.
      return new NextResponse("Sign in to do this.", {
        status: 401,
        headers: { "WWW-Authenticate": 'Basic realm="Deal Radar"' },
      });
    }

    if (
      startsWith(pathname, OWNER_API_PATHS) ||
      OWNER_API_PREFIXES.some((prefix) => pathname.startsWith(prefix))
    ) {
      return new NextResponse("Sign in to see this.", { status: 403 });
    }

    return onward(request, "public");
  }

  if (startsWith(pathname, OWNER_PAGES)) {
    const login = new URL("/login", request.url);

    login.searchParams.set("next", pathname);

    return NextResponse.redirect(login);
  }

  // A first visit lands on the introduction; "Continue as guest" sets the cookie
  // that skips it from then on.
  if (pathname === "/" && !request.cookies.get(VISITOR_COOKIE)) {
    return NextResponse.redirect(new URL("/welcome", request.url));
  }

  return onward(request, "public");
}

export const config = {
  // Everything but Next's own static assets, so the proxied API routes are
  // covered too — gating only the pages would leave the endpoints wide open.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
