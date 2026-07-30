"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AskBox } from "@/components/AskBox";
import { CandidateRow } from "@/components/CandidateRow";
import {
  VERDICTS,
  VERDICT_LABEL,
  buildQuery,
  type Candidate,
  type CandidateList,
  type Meta,
} from "@/lib/api";

export default function Home() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [unreachable, setUnreachable] = useState(false);

  const [theme, setTheme] = useState<string>("");
  const [verdicts, setVerdicts] = useState<string[]>(["fits", "maybe"]);
  const [since, setSince] = useState<string>("");
  const [until, setUntil] = useState<string>("");
  const [unreadOnly, setUnreadOnly] = useState(false);

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
  }, [query]);

  /** Update one row in place rather than refetching the whole list. */
  const handleRead = useCallback(
    (accession: string) => {
      setCandidates((current) =>
        current.map((item) =>
          item.accession === accession
            ? { ...item, viewed_at: new Date().toISOString() }
            : item,
        ),
      );

      void loadMeta();
    },
    [loadMeta],
  );

  function toggleVerdict(verdict: string) {
    setVerdicts((current) =>
      current.includes(verdict)
        ? current.filter((item) => item !== verdict)
        : [...current, verdict],
    );
  }

  async function markAllRead() {
    await fetch(
      `/api/viewed${theme ? `?theme=${encodeURIComponent(theme)}` : ""}`,
      { method: "POST" },
    );

    setCandidates((current) =>
      current.map((item) =>
        item.viewed_at
          ? item
          : { ...item, viewed_at: new Date().toISOString() },
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
          cd ~/deal-radar{"\n"}
          .venv/bin/uvicorn src.api:app --port 8100
        </pre>
      </main>
    );
  }

  const unread = meta?.unread ?? 0;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-[var(--color-rule)]">
        <div className="mx-auto flex max-w-3xl flex-wrap items-baseline justify-between gap-x-8 gap-y-2 px-8 pt-10 pb-6">
          <h1 className="font-display text-[1.75rem] leading-none tracking-tight">
            Deal Radar
          </h1>

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
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 px-8">
        <section className="flex flex-wrap items-end gap-x-8 gap-y-4 border-b border-[var(--color-rule)] py-5">
          <label>
            <span className="label mb-1 block">Domain</span>
            <select
              value={theme}
              onChange={(event) => setTheme(event.target.value)}
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
              onChange={(event) => setSince(event.target.value)}
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
              onChange={(event) => setUntil(event.target.value)}
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
              onChange={(event) => setUnreadOnly(event.target.checked)}
              className="accent-[var(--color-ink)]"
            />
            Unread only
          </label>

          <div className="ml-auto flex items-baseline gap-5">
            {(since || until) && (
              <button
                type="button"
                onClick={() => {
                  setSince("");
                  setUntil("");
                }}
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
