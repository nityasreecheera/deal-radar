import { NextResponse, type NextRequest } from "next/server";

import { findGuest } from "@/lib/guests";
import {
  SESSION_COOKIE,
  SESSION_MAX_AGE_SECONDS,
  matches,
  signSession,
} from "@/lib/session";

/**
 * A relative redirect, and 303 so the browser follows with GET rather than
 * re-posting the password.
 *
 * Relative on purpose. Behind the Cloudflare or Tailscale tunnel `request.url`
 * is the VM's own address, so building an absolute URL from it sends people to
 * localhost:3100 — which works perfectly when testing on the VM and is a dead
 * link for everyone else.
 */
function seeOther(location: string) {
  return new NextResponse(null, { status: 303, headers: { Location: location } });
}

/**
 * Exchange the shared password for a session cookie.
 *
 * A form post rather than JSON, so the login page works without JavaScript and
 * the browser's own password manager can offer to remember it.
 */
export async function POST(request: NextRequest) {
  const user = process.env.SHARE_USER;
  const password = process.env.SHARE_PASSWORD;

  const form = await request.formData();
  const next = String(form.get("next") || "/");

  // Only ever send someone back to a path on this site. An open redirect is a
  // small hole that turns a private tool into a phishing hop.
  const destination = next.startsWith("/") && !next.startsWith("//") ? next : "/";

  if (!user || !password) {
    return seeOther(destination);
  }

  const given = String(form.get("password") || "");
  const givenUser = String(form.get("user") || user);

  // A named guest signs in with the name alone. It grants a read-only session
  // that ends on the guest's own date rather than the usual fortnight, so
  // access lapses without anyone having to remember to remove it.
  const guest = given ? null : findGuest(String(form.get("user") || ""));

  if (guest) {
    const response = seeOther(destination);

    response.cookies.set(
      SESSION_COOKIE,
      await signSession(password, Date.now(), guest.expiresAt, "guest"),
      {
        httpOnly: true,
        sameSite: "lax",
        path: "/",
        maxAge: Math.floor((guest.expiresAt - Date.now()) / 1000),
        secure: request.nextUrl.protocol === "https:",
      },
    );

    return response;
  }

  if (!matches(givenUser, user) || !matches(given, password)) {
    const back = new URLSearchParams({ error: "1" });

    if (next !== "/") back.set("next", next);

    return seeOther(`/login?${back}`);
  }

  const response = seeOther(destination);

  response.cookies.set(SESSION_COOKIE, await signSession(password), {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
    // The tunnel is HTTPS; local development over plain HTTP is not.
    secure: request.nextUrl.protocol === "https:",
  });

  return response;
}
