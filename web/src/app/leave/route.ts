import { NextResponse } from "next/server";

/**
 * "Exit" for a visitor: forget "Get started" and go back to the introduction.
 *
 * A visitor has no session to end — reading is open to everyone — so this only
 * clears the cookie that skips the introduction. The owner's "Sign out" is a
 * different thing and lives at /auth/logout.
 *
 * Relative redirect, as in the other auth routes: behind the tunnel an absolute
 * URL built from the request would point at the server's own address.
 */
export function GET() {
  const response = new NextResponse(null, {
    status: 303,
    headers: { Location: "/welcome" },
  });

  response.cookies.delete("radar_visitor");

  return response;
}
