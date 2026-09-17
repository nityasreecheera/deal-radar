/**
 * Mint an invite link.
 *
 *   node scripts/invite.mjs            # 7 days
 *   node scripts/invite.mjs --days 14
 *
 * Reads the share password to sign with and never prints it. The link is the
 * only thing that comes out, and it is the only thing that needs sending: the
 * person who clicks it gets a session that ends on the date shown, and never
 * learns the password.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const envPath = join(here, "..", "web", ".env.local");

function read(name) {
  const line = readFileSync(envPath, "utf8")
    .split("\n")
    .find((row) => row.startsWith(`${name}=`));

  return line?.slice(name.length + 1).trim().replace(/^["']|["']$/g, "");
}

const password = read("SHARE_PASSWORD");

if (!password) {
  console.error(`No SHARE_PASSWORD in ${envPath} — nothing to sign with.`);
  process.exit(1);
}

const argument = process.argv.indexOf("--days");
const days = argument === -1 ? 7 : Number(process.argv[argument + 1]);

if (!Number.isFinite(days) || days <= 0) {
  console.error("--days must be a positive number of days.");
  process.exit(1);
}

const base = read("SITE_URL") ?? "https://radar.humpback-pleco.ts.net";
const expiresAt = Date.now() + days * 24 * 60 * 60 * 1000;
const payload = `invite:${expiresAt}`;

const key = await crypto.subtle.importKey(
  "raw",
  new TextEncoder().encode(password),
  { name: "HMAC", hash: "SHA-256" },
  false,
  ["sign"],
);

const signature = Buffer.from(
  await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload)),
)
  .toString("base64")
  .replace(/\+/g, "-")
  .replace(/\//g, "_")
  .replace(/=+$/, "");

console.log(`\n${base}/invite?t=${encodeURIComponent(`${payload}.${signature}`)}\n`);
console.log(`Valid for ${days} days — until ${new Date(expiresAt).toUTCString()}.`);
console.log("Anyone with this link is in until then. Rotating SHARE_PASSWORD kills it early.\n");
