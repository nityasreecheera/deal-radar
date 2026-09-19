/**
 * Mint an API token for someone else's program.
 *
 *   node scripts/token.mjs --name acme --scope read     --days 90
 *   node scripts/token.mjs --name acme --scope sandbox  --days 30
 *
 * Scopes:
 *   read     every GET — the judgements, the analysis, the companies.
 *            No writes, no /api/chat.
 *   sandbox  /api/try only. They run their own criteria and see nothing
 *            anyone else concluded.
 *
 * Reads the share password to sign with and never prints it. Rotating that
 * password revokes every token ever minted, which is the only revocation there
 * is — nothing is stored server-side.
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

function flag(name, fallback) {
  const at = process.argv.indexOf(`--${name}`);

  return at === -1 ? fallback : process.argv[at + 1];
}

const password = read("SHARE_PASSWORD");

if (!password) {
  console.error(`No SHARE_PASSWORD in ${envPath} — nothing to sign with.`);
  process.exit(1);
}

const name = flag("name");
const scope = flag("scope", "sandbox");
const days = Number(flag("days", "90"));

if (!name || !/^[a-z0-9-]{1,32}$/i.test(name)) {
  console.error("--name is required: letters, digits and dashes, up to 32.");
  process.exit(1);
}

if (scope !== "read" && scope !== "sandbox") {
  console.error("--scope must be 'read' or 'sandbox'.");
  process.exit(1);
}

if (!Number.isFinite(days) || days <= 0) {
  console.error("--days must be a positive number of days.");
  process.exit(1);
}

const base = read("SITE_URL") ?? "https://radar.humpback-pleco.ts.net";
const expiresAt = Date.now() + days * 24 * 60 * 60 * 1000;
const payload = `token:${name}:${scope}:${expiresAt}`;

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

const token = `${payload}.${signature}`;

console.log(`\nToken for "${name}" — scope ${scope}, valid ${days} days`);
console.log(`Expires ${new Date(expiresAt).toUTCString()}\n`);
console.log(token);
console.log(`\nUse it like this:\n`);
console.log(`  curl -H "Authorization: Bearer $TOKEN" \\`);
console.log(
  scope === "read"
    ? `    "${base}/api/candidates?verdict=fits&limit=20"`
    : `    -X POST -H "Content-Type: application/json" \\\n` +
      `    -d '{"include":["data centre cooling"]}' \\\n` +
      `    "${base}/api/try"`,
);
console.log(
  `\nAnyone holding this is in until it expires. Rotating SHARE_PASSWORD revokes it.\n`,
);
