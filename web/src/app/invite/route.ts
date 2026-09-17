import { NextResponse, type NextRequest } from "next/server";

import {
  SESSION_COOKIE,
  signSession,
  verifyInvite,
} from "@/lib/session";

/**
 * Exchange an invite link for a session that ends when the invite does.
 *
 * For showing the radar to someone once — a reviewer, an interviewer — without
 * handing over the shared password. They click the link, they are in, and on the
 * date it was minted for they are out again whether or not anybody remembered.
 *
 * The session inherits the invite's expiry rather than the usual fortnight, so a
 * link clicked on its last day grants a day, not two more weeks. Nothing is
 * stored: the expiry is inside the signed payload, so it cannot be edited by
 * whoever holds the link, and rotating the share password revokes every
 * outstanding invite at once.
 */
function seeOther(location: string) {
  return new NextResponse(null, { status: 303, headers: { Location: location } });
}

export async function GET(request: NextRequest) {
  const password = process.env.SHARE_PASSWORD;
  const token = request.nextUrl.searchParams.get("t") ?? undefined;

  const expiresAt = password
    ? await verifyInvite(token, password)
    : null;

  if (expiresAt === null) {
    // Expired and forged land in the same place on purpose. Telling the holder
    // which one it was tells them whether the link was ever real.
    return seeOther("/login?invite=expired");
  }

  const response = seeOther("/");
  const remaining = Math.floor((expiresAt - Date.now()) / 1000);

  response.cookies.set(SESSION_COOKIE, await signSession(password!, Date.now(), expiresAt), {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: remaining,
    secure: request.nextUrl.protocol === "https:",
  });

  return response;
}
