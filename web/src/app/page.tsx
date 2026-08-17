"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { AskBox } from "@/components/AskBox";
import { CandidateRow } from "@/components/CandidateRow";
import { LogoutButton } from "@/components/LogoutButton";
import {
  VERDICTS,
  VERDICT_LABEL,
  buildQuery,
  type Candidate,
  type CandidateList,
  type Meta,
} from "@/lib/api";

/**
 * The list.
 *
 * Filters live in the URL rather than in component state. That is what makes
 * the back button from a company page work: leaving the list and returning has
 * to land on the list you were looking at, not on the default view. It also
 * makes a filtered list something you can send someone.
 */

const DEFAULT_VERDICTS = ["fits", "maybe"];

export default function Home() {
  // useSearchParams forces client rendering up to the nearest boundary, and a
  // production build fails outright without one.
  return (
    <Suspense fallback={<p className="label px-8 py-10">Loading</p>}>
      <CandidateList />
    </Suspense>
  );
}

function CandidateList() {
  const router = useRouter();
  const params = useSearchParams();

  const [meta, setMeta] = useState<Meta | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [unreachable, setUnreachable] = useState(false);
  const [reloads, setReloads] = useState(0);

  const theme = params.get("theme") ?? "";
  const since = params.get("since") ?? "";
  const until = params.get("until") ?? "";
  const unreadOnly = params.get("unread") === "1";

  // An explicitly empty `verdict` means "none selected", which is different
  // from the parameter being absent. Reading it as absent would silently
  // re-select the defaults and make deselecting everything impossible.
  const verdicts = useMemo(() => {
    const raw = params.get("verdict");

    if (raw === null) return DEFAULT_VERDICTS;

    return raw === "" ? [] : raw.split(",");
  }, [params]);

  /** Rewrite the URL. Everything reads back out of it. */
  const setFilters = useCallback(
    (changes: Record<string, string | null>) => {
      const next = new URLSearchParams(params.toString());

      for (const [key, value] of Object.entries(changes)) {
        if (value === null) next.delete(key);
        else next.set(key, value);
      }

      // replace, not push: a back button that walks through every filter
      // fiddle before leaving the page is worse than useless.
      router.replace(next.toString() ? `/?${next}` : "/", { scroll: false });
    },
    [params, router],
  );

  const query = useMemo(
    () =>
      buildQuery({
        verdict: verdicts,
        theme: theme || undefined,
        since: since || undefined,
        until: until || undefined,
        unreadOnly,
        limit: 200,
      }),
    [verdicts, theme, since, until, unreadOnly],
  );

  const loadMeta = useCallback(async () => {
    try {
      const response = await fetch("/api/meta", { cache: "no-store" });

      if (!response.ok) throw new Error(String(response.status));

      setMeta((await response.json()) as Meta);
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, []);

  useEffect(() => {
    void loadMeta();
  }, [loadMeta]);

  // Coming back from a company page has to show it as read. The page marked it,
  // not the list, and returning does not necessarily remount this component —
  // so refresh when the tab regains attention rather than trusting the mount.
  useEffect(() => {
    function refresh() {
      if (document.visibilityState === "visible") {
        setReloads((n) => n + 1);
        void loadMeta();
      }
    }

    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);

    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [loadMeta]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);

      try {
        const response = await fetch(`/api/candidates${query}`, {
          cache: "no-store",
        });

        if (!response.ok) throw new Error(String(response.status));

        const body = (await response.json()) as CandidateList;

        if (!cancelled) {
          // Optional in the generated schema because the Pydantic field has a
          // default_factory, even though the API always sends it.
          setCandidates(body.candidates ?? []);
          setUnreachable(false);
        }
      } catch {
        if (!cancelled) setUnreachable(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [query, reloads]);

  /** Update one row in place rather than refetching the whole list. */
  const handleRead = useCallback((accession: string) => {
    setCandidates((current) =>
      current.map((item) =>
        item.accession === accession
          ? { ...item, viewed_at: new Date().toISOString() }
          : item,
      ),
    );
  }, []);

  function toggleVerdict(verdict: string) {
    const next = verdicts.includes(verdict)
      ? verdicts.filter((item) => item !== verdict)
      : [...verdicts, verdict];

    setFilters({ verdict: next.join(",") });
  }

  async function markAllRead() {
    await fetch(
      `/api/viewed${theme ? `?theme=${encodeURIComponent(theme)}` : ""}`,
      { method: "POST" },
    );

    setCandidates((current) =>
      current.map((item) =>
        item.viewed_at ? item : { ...item, viewed_at: new Date().toISOString() },
      ),
    );

    void loadMeta();
  }

  if (unreachable) {
    return (
      <main className="mx-auto max-w-xl px-8 py-24">
        <h2 className="font-display text-xl">The API is not running</h2>
        <p className="mt-3 text-sm text-[var(--color-ink-soft)]">
          Start it on the VM, then reload.
        </p>
        <pre className="tabular mt-4 overflow-x-auto border-l-2 border-[var(--color-rule)] pl-4 text-xs text-[var(--color-ink-faint)]">
          systemctl --user restart radar-api
        </pre>
      </main>
    );
  }

  const unread = meta?.unread ?? 0;

  // Handed to each row so the company page can send you back to this exact list.
  const from = params.toString();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-[var(--color-rule)]">
        <div className="mx-auto flex max-w-3xl flex-wrap items-baseline justify-between gap-x-8 gap-y-2 px-8 pt-10 pb-6">
          <h1 className="font-display text-[1.75rem] leading-none tracking-tight">
            Deal Radar
          </h1>

          <span className="flex items-baseline gap-5">
            <Link
              href="/criteria"
              className="text-[0.8125rem] text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
            >
              Criteria
            </Link>
            <Link
              href="/analysis"
              className="text-[0.8125rem] text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
            >
              Analysis
            </Link>
          </span>

          <p className="label">
            {meta ? (
              <>
                <span className="tabular text-[var(--color-ink)]">{unread}</span>{" "}
                unread
                <span className="mx-2 text-[var(--color-rule)]">/</span>
                <span className="tabular">{meta.companies_known}</span> known
              </>
            ) : (
              "loading"
            )}
            <span className="mx-2 text-[var(--color-rule)]">/</span>
            <LogoutButton />
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 px-8">
        <section className="flex flex-wrap items-end gap-x-8 gap-y-4 border-b border-[var(--color-rule)] py-5">
          <label>
            <span className="label mb-1 block">Domain</span>
            <select
              value={theme}
              onChange={(event) =>
                setFilters({ theme: event.target.value || null })
              }
              className="field pr-6"
            >
              <option value="">All</option>
              {(meta?.themes ?? []).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span className="label mb-1 block">Filed from</span>
            <input
              type="date"
              value={since}
              min={meta?.earliest_filing ?? undefined}
              max={meta?.latest_filing ?? undefined}
              onChange={(event) =>
                setFilters({ since: event.target.value || null })
              }
              className="field tabular"
            />
          </label>

          <label>
            <span className="label mb-1 block">Until</span>
            <input
              type="date"
              value={until}
              min={meta?.earliest_filing ?? undefined}
              max={meta?.latest_filing ?? undefined}
              onChange={(event) =>
                setFilters({ until: event.target.value || null })
              }
              className="field tabular"
            />
          </label>

          <div className="flex items-baseline gap-4">
            {VERDICTS.map((verdict) => {
              const active = verdicts.includes(verdict);

              return (
                <button
                  key={verdict}
                  type="button"
                  onClick={() => toggleVerdict(verdict)}
                  className={`pb-0.5 text-[0.6875rem] tracking-[0.08em] uppercase transition-colors ${
                    active
                      ? "border-b border-[var(--color-ink)] text-[var(--color-ink)]"
                      : "border-b border-transparent text-[var(--color-ink-faint)] hover:text-[var(--color-ink-soft)]"
                  }`}
                >
                  {VERDICT_LABEL[verdict]}
                </button>
              );
            })}
          </div>

          <label className="flex items-center gap-2 text-[0.75rem] text-[var(--color-ink-soft)]">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(event) =>
                setFilters({ unread: event.target.checked ? "1" : null })
              }
              className="accent-[var(--color-ink)]"
            />
            Unread only
          </label>

          <div className="ml-auto flex items-baseline gap-5">
            {(since || until) && (
              <button
                type="button"
                onClick={() => setFilters({ since: null, until: null })}
                className="text-[0.75rem] text-[var(--color-ink-faint)] hover:text-[var(--color-ink)]"
              >
                clear dates
              </button>
            )}

            {unread > 0 && (
              <button
                type="button"
                onClick={() => void markAllRead()}
                className="text-[0.75rem] text-[var(--color-ink-faint)] hover:text-[var(--color-ink)]"
              >
                mark all read
              </button>
            )}
          </div>
        </section>

        {loading ? (
          <p className="label py-10">Loading</p>
        ) : candidates.length === 0 ? (
          <p className="py-10 text-sm text-[var(--color-ink-faint)]">
            Nothing matches those filters.
            {verdicts.length === 0 && " Choose at least one verdict."}
          </p>
        ) : (
          <>
            <ul className="pb-10">
              {candidates.map((candidate) => (
                <CandidateRow
                  key={candidate.accession}
                  candidate={candidate}
                  from={from}
                  onRead={handleRead}
                />
              ))}
            </ul>

            <p className="label pb-10">
              <span className="tabular">{candidates.length}</span> shown
              {meta?.earliest_filing && (
                <>
                  <span className="mx-2 text-[var(--color-rule)]">/</span>
                  filings on record {meta.earliest_filing} to {meta.latest_filing}
                </>
              )}
            </p>
          </>
        )}
      </main>

      <AskBox theme={theme || null} />
    </div>
  );
}
