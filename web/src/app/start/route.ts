import { NextResponse, type NextRequest } from "next/server";

/**
 * "Continue as guest": remember that this visitor has seen the introduction, and take
 * them to the companies.
 *
 * The cookie grants nothing — it only stops the home page redirecting to
 * /welcome. Reading is open to everyone either way.
 *
 * A relative redirect, for the same reason as the login route: behind the tunnel
 * `request.url` is the server's own address, and an absolute URL built from it is
 * a dead link for everyone else.
 */
export function GET(request: NextRequest) {
  const response = new NextResponse(null, { status: 303, headers: { Location: "/" } });

  response.cookies.set("radar_visitor", "1", {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 365 * 24 * 60 * 60,
    secure: request.nextUrl.protocol === "https:",
  });

  return response;
}
