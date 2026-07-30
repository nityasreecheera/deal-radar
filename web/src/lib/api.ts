import type { components } from "@/types/api";

type Schemas = components["schemas"];

// Generated from the Pydantic models via the OpenAPI schema. Regenerate after
// changing a model:  npm run gen:types   (needs the API running)
export type Candidate = Schemas["StoredCandidate"];
export type Meta = Schemas["Meta"];
export type CandidateList = Schemas["CandidateList"];
export type ChatAnswer = Schemas["ChatAnswer"];
export type Verdict = Candidate["verdict"];

export const VERDICTS: Verdict[] = ["fits", "maybe", "unknown", "no_fit"];

export const VERDICT_LABEL: Record<Verdict, string> = {
  fits: "Fits",
  maybe: "Maybe",
  unknown: "Unknown",
  no_fit: "No fit",
};

export const VERDICT_MARK: Record<Verdict, string> = {
  fits: "✓",
  maybe: "~",
  unknown: "?",
  no_fit: "✗",
};

// Server components reach the API directly; the browser goes through the
// rewrite in next.config.ts.
const SERVER_BASE = process.env.API_BASE_URL ?? "http://127.0.0.1:8100";

export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; reason: "missing" | "unreachable"; message: string };

async function get<T>(path: string): Promise<Result<T>> {
  let response: Response;

  try {
    response = await fetch(`${SERVER_BASE}${path}`, { cache: "no-store" });
  } catch {
    // Almost always the API simply is not running yet.
    return { ok: false, reason: "unreachable", message: "Could not reach the API." };
  }

  if (response.status === 404) {
    return { ok: false, reason: "missing", message: "Not found." };
  }

  if (!response.ok) {
    return {
      ok: false,
      reason: "unreachable",
      message: `The API returned ${response.status}.`,
    };
  }

  return { ok: true, data: (await response.json()) as T };
}

export const getMeta = () => get<Meta>("/api/meta");

export type CandidateFilters = {
  verdict?: string[];
  theme?: string;
  since?: string;
  until?: string;
  unreadOnly?: boolean;
  limit?: number;
};

export function buildQuery(filters: CandidateFilters): string {
  const params = new URLSearchParams();

  for (const verdict of filters.verdict ?? []) {
    params.append("verdict", verdict);
  }

  if (filters.theme) params.set("theme", filters.theme);
  if (filters.since) params.set("since", filters.since);
  if (filters.until) params.set("until", filters.until);
  if (filters.unreadOnly) params.set("unread_only", "true");
  if (filters.limit) params.set("limit", String(filters.limit));

  const query = params.toString();

  return query ? `?${query}` : "";
}

export const getCandidates = (filters: CandidateFilters = {}) =>
  get<CandidateList>(`/api/candidates${buildQuery(filters)}`);

/** Amounts as an analyst reads them, not as they are stored. */
export function formatAmount(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return "undisclosed";

  if (amount >= 1_000_000) {
    return `$${(amount / 1_000_000).toFixed(1)}M`.replace(".0M", "M");
  }

  return `$${Math.round(amount / 1_000)}k`;
}

export function formatLocation(candidate: Candidate): string {
  const city = candidate.city
    ? candidate.city.charAt(0) + candidate.city.slice(1).toLowerCase()
    : "";
  const state = candidate.state ?? "";

  if (city && state) return `${city}, ${state}`;

  return city || state || "location unknown";
}

/**
 * Whether nobody has read this yet.
 *
 * Derived from viewed_at rather than from an `is_unread` field: that exists on
 * the Python model as a property, and Pydantic does not serialise properties, so
 * it never reaches the wire.
 */
export function isUnread(candidate: Candidate): boolean {
  return !candidate.viewed_at;
}

/**
 * Link to the filing on EDGAR.
 *
 * Built here rather than read from the API for the same reason as isUnread: the
 * Python model exposes it as a property, and Pydantic does not serialise
 * properties, so it never reaches the wire.
 */
export function filingUrl(candidate: Candidate): string | null {
  if (!candidate.cik) return null;

  const cik = String(Number(candidate.cik));
  const accession = candidate.accession.replace(/-/g, "");

  return `https://www.sec.gov/Archives/edgar/data/${cik}/${accession}/primary_doc.xml`;
}

/**
 * Styling for a row.
 *
 * Read rows are greyed; unread rows carry their verdict's colour. The contrast
 * is the point — the eye should find the unread ones without reading anything.
 */
export function rowStyle(candidate: Candidate): string {
  if (!isUnread(candidate)) {
    return "border-slate-200 bg-slate-50 text-slate-400";
  }

  switch (candidate.verdict) {
    case "fits":
      return "border-emerald-300 bg-emerald-50 text-slate-900";
    case "maybe":
      return "border-sky-300 bg-sky-50 text-slate-900";
    default:
      return "border-slate-300 bg-white text-slate-700";
  }
}

export function badgeStyle(candidate: Candidate): string {
  if (candidate.viewed_at) {
    return "bg-slate-200 text-slate-500 ring-slate-300";
  }

  switch (candidate.verdict) {
    case "fits":
      return "bg-emerald-100 text-emerald-800 ring-emerald-300";
    case "maybe":
      return "bg-sky-100 text-sky-800 ring-sky-300";
    default:
      return "bg-slate-100 text-slate-600 ring-slate-300";
  }
}
