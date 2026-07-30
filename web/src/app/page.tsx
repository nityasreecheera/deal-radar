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
    await fetch(`/api/viewed${theme ? `?theme=${encodeURIComponent(theme)}` : ""}`, {
      method: "POST",
    });

    setCandidates((current) =>
      current.map((item) =>
        item.viewed_at ? item : { ...item, viewed_at: new Date().toISOString() },
      ),
    );

    void loadMeta();
  }

  if (unreachable) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-6">
          <h2 className="font-semibold text-amber-900">The API is not running</h2>
          <p className="mt-2 text-sm text-amber-800">Start it on the VM, then reload:</p>
          <pre className="mt-2 overflow-x-auto rounded bg-amber-900/90 p-3 text-xs text-amber-50">
            cd ~/deal-radar{"\n"}
            .venv/bin/uvicorn src.api:app --port 8100
          </pre>
        </div>
      </main>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-4xl flex-wrap items-baseline justify-between gap-3">
          <h1 className="font-semibold tracking-tight">Deal Radar</h1>

          <p className="text-sm text-slate-500">
            {meta ? (
              <>
                {meta.unread} unread · {meta.companies_known} companies known
                {meta.thesis_name ? ` · ${meta.thesis_name}` : ""}
              </>
            ) : (
              "loading…"
            )}
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-6">
        <section className="mb-6 space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-end gap-4">
            <label className="text-xs">
              <span className="mb-1 block uppercase tracking-wide text-slate-500">
                Theme
              </span>
              <select
                value={theme}
                onChange={(event) => setTheme(event.target.value)}
                className="rounded border border-slate-300 px-2 py-1 text-sm"
              >
                <option value="">All themes</option>
                {(meta?.themes ?? []).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>

            <label className="text-xs">
              <span className="mb-1 block uppercase tracking-wide text-slate-500">
                Filed from
              </span>
              <input
                type="date"
                value={since}
                min={meta?.earliest_filing ?? undefined}
                max={meta?.latest_filing ?? undefined}
                onChange={(event) => setSince(event.target.value)}
                className="rounded border border-slate-300 px-2 py-1 text-sm"
              />
            </label>

            <label className="text-xs">
              <span className="mb-1 block uppercase tracking-wide text-slate-500">
                to
              </span>
              <input
                type="date"
                value={until}
                min={meta?.earliest_filing ?? undefined}
                max={meta?.latest_filing ?? undefined}
                onChange={(event) => setUntil(event.target.value)}
                className="rounded border border-slate-300 px-2 py-1 text-sm"
              />
            </label>

            {(since || until) && (
              <button
                type="button"
                onClick={() => {
                  setSince("");
                  setUntil("");
                }}
                className="text-xs text-slate-500 underline"
              >
                clear dates
              </button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <div className="flex flex-wrap gap-2">
              {VERDICTS.map((verdict) => (
                <button
                  key={verdict}
                  type="button"
                  onClick={() => toggleVerdict(verdict)}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    verdicts.includes(verdict)
                      ? "border-slate-800 bg-slate-800 text-white"
                      : "border-slate-300 text-slate-600"
                  }`}
                >
                  {VERDICT_LABEL[verdict]}
                </button>
              ))}
            </div>

            <label className="flex items-center gap-2 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={unreadOnly}
                onChange={(event) => setUnreadOnly(event.target.checked)}
              />
              Unread only
            </label>

            {(meta?.unread ?? 0) > 0 && (
              <button
                type="button"
                onClick={() => void markAllRead()}
                className="ml-auto text-xs text-slate-500 underline"
              >
                mark all read
              </button>
            )}
          </div>

          {meta?.earliest_filing && (
            <p className="text-xs text-slate-400">
              Filings on record: {meta.earliest_filing} to {meta.latest_filing}
            </p>
          )}
        </section>

        {loading ? (
          <p className="text-sm text-slate-400">Loading…</p>
        ) : candidates.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 p-6 text-sm text-slate-500">
            Nothing matches those filters.
            {verdicts.length === 0 && " Pick at least one verdict."}
          </p>
        ) : (
          <ul className="space-y-2">
            {candidates.map((candidate) => (
              <CandidateRow
                key={candidate.accession}
                candidate={candidate}
                onRead={handleRead}
              />
            ))}
          </ul>
        )}
      </main>

      <AskBox theme={theme || null} />
    </div>
  );
}
