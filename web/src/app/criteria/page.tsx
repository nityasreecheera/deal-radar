"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { RunNow } from "@/components/RunNow";
import { type Thesis } from "@/lib/api";

/**
 * The criteria, and the ability to change them.
 *
 * This is the only page that writes something the radar depends on. Everything
 * else records what a person thought; this decides what reaches them tomorrow
 * morning. So it is deliberately plain, shows the whole of each thesis rather
 * than a summary, and never saves without being asked.
 *
 * Validation lives on the server, where the same model the pipeline reads is
 * the thing that accepts or rejects an edit. A rule enforced only in a form is
 * a rule that stops existing the moment anyone uses curl.
 */

function empty(): Thesis {
  return {
    domain: "",
    name: "",
    description: "",
    include: [],
    exclude: [],
    sec_industry_groups: ["Other Technology"],
  };
}

export default function CriteriaPage() {
  const [theses, setTheses] = useState<Thesis[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<Thesis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const response = await fetch("/api/theses", { cache: "no-store" });

      if (response.ok) setTheses((await response.json()) as Thesis[]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    if (!draft) return;

    setSaving(true);
    setError(null);

    try {
      const response = await fetch("/api/theses", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thesis: draft,
          // Absent for a new one. The server needs the difference: without it,
          // saving a thesis whose name already exists would overwrite the
          // other rather than being refused.
          original_domain: editing === "new" ? null : editing,
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);

        setError(
          body?.detail?.errors?.[0] ??
            "That could not be saved. Check the domain name and that there is at least one thing to look for.",
        );

        return;
      }

      setEditing(null);
      setDraft(null);
      await load();
    } catch {
      setError("Could not reach the server.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(domain: string) {
    const sure = window.confirm(
      `Delete the ${domain} criteria?\n\nCompanies already judged under it are kept — this only stops it running from now on.`,
    );

    if (!sure) return;

    await fetch(`/api/theses/${encodeURIComponent(domain)}`, {
      method: "DELETE",
    });

    await load();
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-[var(--color-rule)]">
        <div className="mx-auto max-w-3xl px-8 pt-8 pb-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-[0.8125rem] text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
          >
            <span aria-hidden>←</span> All companies
          </Link>

          <h1 className="font-display mt-6 text-[1.75rem] leading-none tracking-tight">
            Criteria
          </h1>

          <p className="mt-3 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
            What each domain looks for. These decide what reaches your inbox
            tomorrow morning, so changes take effect on the next run — there is
            nothing to retrain and no model involved. Run now to try a change
            on past filings instead of waiting.
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 space-y-8 px-8 py-10">
        {loading ? (
          <p className="label">Loading</p>
        ) : (
          <>
            {theses.map((thesis) =>
              editing === thesis.domain ? (
                <Editor
                  key={thesis.domain}
                  draft={draft ?? thesis}
                  onChange={setDraft}
                  onSave={save}
                  onCancel={() => {
                    setEditing(null);
                    setDraft(null);
                    setError(null);
                  }}
                  saving={saving}
                  error={error}
                />
              ) : (
                <Summary
                  key={thesis.domain}
                  thesis={thesis}
                  onEdit={() => {
                    setEditing(thesis.domain);
                    setDraft({ ...thesis });
                    setError(null);
                  }}
                  onDelete={() => void remove(thesis.domain)}
                />
              ),
            )}

            {editing === "new" ? (
              <Editor
                draft={draft ?? empty()}
                onChange={setDraft}
                onSave={save}
                onCancel={() => {
                  setEditing(null);
                  setDraft(null);
                  setError(null);
                }}
                saving={saving}
                error={error}
              />
            ) : (
              <button
                type="button"
                onClick={() => {
                  setEditing("new");
                  setDraft(empty());
                  setError(null);
                }}
                className="rounded border border-[var(--color-rule)] px-4 py-2 text-sm text-[var(--color-ink-soft)] transition-colors hover:border-[var(--color-ink-soft)] hover:text-[var(--color-ink)]"
              >
                Add a domain
              </button>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function Summary({
  thesis,
  onEdit,
  onDelete,
}: {
  thesis: Thesis;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const [running, setRunning] = useState(false);

  return (
    <section className="border-t-2 border-[var(--color-ink)] pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <h2 className="font-display text-[1.125rem]">{thesis.domain}</h2>

        <div className="flex items-baseline gap-4 text-[0.8125rem]">
          <button
            type="button"
            onClick={() => setRunning(true)}
            className="text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
          >
            Run now
          </button>
          <button
            type="button"
            onClick={onEdit}
            className="text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-nofit)]"
          >
            Delete
          </button>
        </div>
      </div>

      <p className="mt-1 text-sm text-[var(--color-ink-soft)]">{thesis.name}</p>

      <p className="mt-3 max-w-2xl text-sm text-[var(--color-ink-soft)]">
        {thesis.description}
      </p>

      <div className="mt-4 grid gap-6 sm:grid-cols-2">
        <div>
          <p className="label mb-1.5">Looking for</p>
          <ul className="space-y-1">
            {(thesis.include ?? []).map((line) => (
              <li key={line} className="text-sm text-[var(--color-ink)]">
                <span className="text-[var(--color-fits)]">+</span> {line}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p className="label mb-1.5">Ruled out</p>
          <ul className="space-y-1">
            {(thesis.exclude ?? []).map((line) => (
              <li key={line} className="text-sm text-[var(--color-ink-soft)]">
                <span className="text-[var(--color-ink-faint)]">−</span> {line}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <p className="mt-4 text-[0.75rem] text-[var(--color-ink-faint)]">
        Searches {(thesis.sec_industry_groups ?? []).join(", ")} · minimum raise{" "}
        <span className="tabular">
          ${(thesis.filters?.min_offering_amount ?? 0).toLocaleString()}
        </span>
      </p>

      {running && <RunNow domain={thesis.domain} onClose={() => setRunning(false)} />}
    </section>
  );
}

function Editor({
  draft,
  onChange,
  onSave,
  onCancel,
  saving,
  error,
}: {
  draft: Thesis;
  onChange: (next: Thesis) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
}) {
  // Lists are edited as one item per line. A row of tag chips looks better and
  // is worse to use when the whole job is rewriting six sentences.
  const set = (changes: Partial<Thesis>) => onChange({ ...draft, ...changes });

  const lines = (value: string) =>
    value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);

  return (
    <section className="border-t-2 border-[var(--color-fits)] pt-4">
      <div className="space-y-4">
        <Field
          label="Domain"
          hint="Short label, shown in the dropdown — Healthcare, Fintech, Energy."
        >
          <input
            value={draft.domain}
            onChange={(event) => set({ domain: event.target.value })}
            className="field w-full"
          />
        </Field>

        <Field label="Full name" hint="A sentence describing the domain.">
          <input
            value={draft.name}
            onChange={(event) => set({ name: event.target.value })}
            className="field w-full"
          />
        </Field>

        <Field
          label="Description"
          hint="What kind of company belongs here. The model reads this."
        >
          <textarea
            value={draft.description}
            onChange={(event) => set({ description: event.target.value })}
            rows={3}
            className="field w-full resize-y"
          />
        </Field>

        <Field label="Looking for" hint="One per line. At least one is required.">
          <textarea
            value={(draft.include ?? []).join("\n")}
            onChange={(event) => set({ include: lines(event.target.value) })}
            rows={6}
            className="field w-full resize-y"
          />
        </Field>

        <Field label="Ruled out" hint="One per line.">
          <textarea
            value={(draft.exclude ?? []).join("\n")}
            onChange={(event) => set({ exclude: lines(event.target.value) })}
            rows={5}
            className="field w-full resize-y"
          />
        </Field>

        <Field
          label="SEC industry boxes to search"
          hint="One per line, spelled exactly as the SEC does — it writes 'and', not '&', and a mistyped box finds nothing at all."
        >
          <textarea
            value={(draft.sec_industry_groups ?? []).join("\n")}
            onChange={(event) =>
              set({ sec_industry_groups: lines(event.target.value) })
            }
            rows={4}
            className="field w-full resize-y"
          />
        </Field>

        <Field
          label="Minimum raise"
          hint="Filings smaller than this are dropped before anything is looked up."
        >
          <input
            type="number"
            value={draft.filters?.min_offering_amount ?? 0}
            onChange={(event) =>
              set({
                filters: {
                  // Spelled out rather than spread, so the defaults the pipeline
                  // relies on cannot go missing through a form that never
                  // showed them.
                  exclude_amendments: draft.filters?.exclude_amendments ?? true,
                  exclude_name_patterns:
                    draft.filters?.exclude_name_patterns ?? [],
                  require_disclosed_amount:
                    draft.filters?.require_disclosed_amount ?? false,
                  min_offering_amount: Number(event.target.value) || 0,
                },
              })
            }
            className="field w-48 tabular"
          />
        </Field>
      </div>

      {error && (
        <p className="mt-4 border-l-2 border-[var(--color-nofit)] pl-3 text-sm text-[var(--color-ink)]">
          {error}
        </p>
      )}

      <div className="mt-5 flex items-center gap-4">
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="rounded border border-[var(--color-ink)] bg-[var(--color-ink)] px-4 py-1.5 text-sm text-[var(--color-paper)] transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {saving ? "Saving" : "Save"}
        </button>

        <button
          type="button"
          onClick={onCancel}
          className="text-sm text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
        >
          Cancel
        </button>
      </div>
    </section>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="label mb-1 block">{label}</span>
      {hint && (
        <span className="mb-1.5 block text-[0.75rem] text-[var(--color-ink-faint)]">
          {hint}
        </span>
      )}
      {children}
    </label>
  );
}
