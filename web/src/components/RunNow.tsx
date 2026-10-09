"use client";

import { useEffect, useState } from "react";

import { type ManualRun, type RunPreview } from "@/lib/api";

/**
 * Run one domain over a range of the archive, now, instead of tomorrow morning.
 *
 * Two steps on purpose. The first only counts — how many companies, how many
 * model calls, how many web searches — and spends nothing. The second spends,
 * and its button says exactly how much it will judge. A run is the one thing on
 * this site that costs money per click, so the click comes after the number.
 */

const MAX_CAP = 100;

// UTC, because the server checks "not in the future" against UTC. A local date
// ahead of it would be refused for the first few hours of someone's morning.
function utcDay(offsetDays = 0): string {
  const day = new Date(Date.now() + offsetDays * 24 * 60 * 60 * 1000);

  return day.toISOString().slice(0, 10);
}

async function errorFrom(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);

  return body?.detail?.errors?.[0] ?? `Something went wrong (${response.status}).`;
}

export function RunNow({ domain, onClose }: { domain: string; onClose: () => void }) {
  const [start, setStart] = useState(utcDay(-30));
  const [end, setEnd] = useState(utcDay());
  const [cap, setCap] = useState(MAX_CAP);

  const [preview, setPreview] = useState<RunPreview | null>(null);
  const [run, setRun] = useState<ManualRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const base = `/api/theses/${encodeURIComponent(domain)}`;

  // Poll until the run is no longer running. The request that started it
  // returned at once; judging takes minutes.
  const runId = run?.id;
  const finished = run !== null && run.status !== "running";

  useEffect(() => {
    if (runId === undefined || finished) return;

    const timer = window.setInterval(async () => {
      const response = await fetch(`/api/runs/${runId}`, { cache: "no-store" }).catch(
        () => null,
      );

      if (response?.ok) setRun((await response.json()) as ManualRun);
    }, 3000);

    return () => window.clearInterval(timer);
  }, [runId, finished]);

  async function check() {
    setBusy(true);
    setError(null);
    setPreview(null);

    try {
      const params = new URLSearchParams({ start_date: start, end_date: end, cap: String(cap) });
      const response = await fetch(`${base}/run-preview?${params}`, { cache: "no-store" });

      if (!response.ok) {
        setError(await errorFrom(response));
        return;
      }

      setPreview((await response.json()) as RunPreview);
    } catch {
      setError("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function go() {
    setBusy(true);
    setError(null);

    try {
      const response = await fetch(`${base}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start_date: start, end_date: end, cap }),
      });

      if (!response.ok) {
        setError(await errorFrom(response));
        return;
      }

      setRun((await response.json()) as ManualRun);
    } catch {
      setError("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const button =
    "rounded border px-3 py-1.5 text-sm transition-colors disabled:opacity-50";

  return (
    <div className="mt-4 rounded border border-[var(--color-rule)] bg-[var(--color-paper-raised)] p-4">
      <div className="flex items-baseline justify-between">
        <p className="label">Run now</p>
        <button
          type="button"
          onClick={onClose}
          className="text-[0.8125rem] text-[var(--color-ink-faint)] hover:text-[var(--color-ink)]"
        >
          Close
        </button>
      </div>

      {run ? (
        <RunStatus run={run} />
      ) : (
        <>
          <p className="mt-2 text-[0.8125rem] text-[var(--color-ink-soft)]">
            Judges stored filings from these dates against the {domain} criteria.
            Companies this domain has already judged are skipped.
          </p>

          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="text-[0.8125rem] text-[var(--color-ink-soft)]">
              From
              <input
                type="date"
                value={start}
                max={end}
                onChange={(event) => {
                  setStart(event.target.value);
                  setPreview(null);
                }}
                className="field mt-1 block"
              />
            </label>

            <label className="text-[0.8125rem] text-[var(--color-ink-soft)]">
              To
              <input
                type="date"
                value={end}
                min={start}
                max={utcDay()}
                onChange={(event) => {
                  setEnd(event.target.value);
                  setPreview(null);
                }}
                className="field mt-1 block"
              />
            </label>

            <label className="text-[0.8125rem] text-[var(--color-ink-soft)]">
              At most
              <input
                type="number"
                min={1}
                max={MAX_CAP}
                value={cap}
                onChange={(event) => {
                  setCap(Math.max(1, Math.min(MAX_CAP, Number(event.target.value) || 1)));
                  setPreview(null);
                }}
                className="field tabular mt-1 block w-24"
              />
            </label>

            <button
              type="button"
              onClick={() => void check()}
              disabled={busy}
              className={`${button} border-[var(--color-rule)] text-[var(--color-ink-soft)] hover:border-[var(--color-ink-soft)] hover:text-[var(--color-ink)]`}
            >
              {busy && !preview ? "Counting…" : "Check what it would do"}
            </button>
          </div>

          {preview && (
            <Preview
              preview={preview}
              busy={busy}
              onRun={() => void go()}
              buttonClass={button}
            />
          )}
        </>
      )}

      {error && <p className="mt-3 text-sm text-[var(--color-maybe)]">{error}</p>}
    </div>
  );
}

function Preview({
  preview,
  busy,
  onRun,
  buttonClass,
}: {
  preview: RunPreview;
  busy: boolean;
  onRun: () => void;
  buttonClass: string;
}) {
  const missing = preview.missing_days ?? [];

  return (
    <div className="mt-4 space-y-2 border-t border-[var(--color-rule)] pt-3 text-sm">
      <p className="tabular text-[var(--color-ink-soft)]">
        {preview.archived} filings stored in these categories · {preview.passed_filters} pass
        the filters · {preview.already_checked} skipped (already judged, or filed twice)
      </p>

      {missing.length > 0 && (
        <p className="text-[var(--color-maybe)]">
          The archive has not read {missing.length} of these days in full
          {missing.length <= 5 ? ` (${missing.join(", ")})` : ""}, so companies filed on them
          are not included.
        </p>
      )}

      {preview.running ? (
        <p className="text-[var(--color-maybe)]">
          A run for {preview.running.theme} is still going. Wait for it to finish.
        </p>
      ) : preview.to_check === 0 ? (
        <p className="text-[var(--color-ink-soft)]">Nothing new to judge in this range.</p>
      ) : (
        <>
          <p>
            This run would judge <span className="tabular">{preview.to_check}</span>{" "}
            {preview.to_check === 1 ? "company" : "companies"}:{" "}
            <span className="tabular">{preview.model_calls}</span> model calls and up to{" "}
            <span className="tabular">{preview.lookups}</span> web searches.
            {preview.left_over > 0 && (
              <>
                {" "}
                Another <span className="tabular">{preview.left_over}</span> would be left for
                a later run.
              </>
            )}
          </p>

          <button
            type="button"
            onClick={onRun}
            disabled={busy}
            className={`${buttonClass} border-[var(--color-ink)] bg-[var(--color-ink)] text-[var(--color-paper)] hover:opacity-90`}
          >
            {busy ? "Starting…" : `Judge ${preview.to_check} now`}
          </button>
        </>
      )}
    </div>
  );
}

function RunStatus({ run }: { run: ManualRun }) {
  const problems = run.problems ?? [];

  if (run.status === "running") {
    return (
      <p className="mt-3 text-sm text-[var(--color-ink-soft)]">
        Running. This can take a few minutes — you can leave this page and the run
        carries on.
      </p>
    );
  }

  const failed = run.status === "failed" || (run.judged === 0 && run.unexamined > 0);

  return (
    <div className="mt-3 space-y-2 text-sm">
      <p className={failed ? "text-[var(--color-maybe)]" : "text-[var(--color-ink)]"}>
        {run.message}
      </p>

      {run.judged > 0 && (
        <p className="tabular text-[var(--color-ink-soft)]">
          {run.fits} fit · {run.maybe} maybe — they are in the company list now.
        </p>
      )}

      {problems.length > 0 && (
        <details className="text-[0.8125rem] text-[var(--color-ink-faint)]">
          <summary className="cursor-pointer">
            {problems.length} {problems.length === 1 ? "problem" : "problems"}
          </summary>
          <ul className="mt-1 space-y-0.5">
            {problems.slice(0, 10).map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
