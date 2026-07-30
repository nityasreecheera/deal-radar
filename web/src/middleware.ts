import { NextResponse, type NextRequest } from "next/server";

// HTTP Basic auth, enforced when SHARE_USER and SHARE_PASSWORD are set.
//
// This exists because the site can be published through a tunnel, and two of its
// endpoints are not harmless: /api/chat spends money on every request, and
// /api/viewed writes. An ungated URL would let anyone holding it run up a bill
// or mark the whole inbox read.
//
// Leave the variables unset for local development and nothing is enforced.
const USER = process.env.SHARE_USER;
const PASSWORD = process.env.SHARE_PASSWORD;

function unauthorized() {
  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Deal Radar"' },
  });
}

/** Compare without leaking length or position through timing. */
function matches(given: string, expected: string): boolean {
  if (given.length !== expected.length) return false;

  let difference = 0;

  for (let index = 0; index < given.length; index += 1) {
    difference |= given.charCodeAt(index) ^ expected.charCodeAt(index);
  }

  return difference === 0;
}

export function middleware(request: NextRequest) {
  if (!USER || !PASSWORD) {
    return NextResponse.next();
  }

  const header = request.headers.get("authorization");

  if (!header?.startsWith("Basic ")) {
    return unauthorized();
  }

  let decoded: string;

  try {
    decoded = atob(header.slice("Basic ".length));
  } catch {
    return unauthorized();
  }

  const separator = decoded.indexOf(":");

  if (separator === -1) {
    return unauthorized();
  }

  if (
    !matches(decoded.slice(0, separator), USER) ||
    !matches(decoded.slice(separator + 1), PASSWORD)
  ) {
    return unauthorized();
  }

  return NextResponse.next();
}

export const config = {
  // Everything but Next's own static assets, so the proxied API routes are
  // covered too — gating only the pages would leave the endpoints wide open.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
