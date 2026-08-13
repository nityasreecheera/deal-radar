import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE } from "@/lib/session";

/**
 * Clear the session.
 *
 * POST rather than GET on purpose: Next prefetches links, and a logout that
 * happens because a browser looked at a link is a bug someone would spend a
 * while not believing.
 */
export async function POST(_request: NextRequest) {
  // Relative, so the tunnel does not send people to the VM's own address.
  const response = new NextResponse(null, {
    status: 303,
    headers: { Location: "/login" },
  });

  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });

  return response;
}
