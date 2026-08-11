"use client";

import { useState } from "react";

import { type Candidate, type Verdict } from "@/lib/api";

/**
 * Where the analyst overrules the model and writes down why.
 *
 * The note matters more than the verdict. A verdict can be re-derived from the
 * filing; the reason someone passed cannot — it came from a conversation, or a
 * hunch, or knowing the team. That's the thing that vanishes, and the thing the
 * whole product exists to stop vanishing.
 *
 * Both save independently. Changing the verdict must not discard a half-written
 * note, and saving a note must not silently confirm a verdict nobody chose.
 *
 * Saving is explicit rather than on blur. This writes a judgement someone will
 * read back months later, and a control that saves when you click away makes it
 * ambiguous whether it took.
 */

const CHOICES: { value: Verdict; label: string }[] = [
  { value: "fits", label: "Fits" },
  { value: "maybe", label: "Maybe" },
  { value: "no_fit", label: "No fit" },
  { value: "unknown", label: "Unknown" },
];

type Saved = "idle" | "saving" | "done" | "failed";

export function DecisionPanel({
  candidate,
  onChange,
}: {
  candidate: Candidate;
  onChange: (updated: Candidate) => void;
}) {
  const [note, setNote] = useState(candidate.user_note ?? "");
  const [state, setState] = useState<Saved>("idle");

  const chosen = candidate.user_verdict ?? null;
  const dirty = note !== (candidate.user_note ?? "");

  async function save(body: Record<string, unknown>) {
    setState("saving");

    try {
      const response = await fetch(
        `/api/candidates/${encodeURIComponent(candidate.accession)}/decision`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );

      if (!response.ok) throw new Error(String(response.status));

      onChange((await response.json()) as Candidate);
      setState("done");
    } catch {
      // Say so rather than showing a tick. A note someone believes is saved and
      // isn't is worse than no note at all.
      setState("failed");
    }
  }

  return (
    <section>
      <h3 className="label mb-2">Your call</h3>

      <div className="mb-3 flex flex-wrap gap-2">
        {CHOICES.map((choice) => {
          const active = chosen === choice.value;

          return (
            <button
              key={choice.value}
              type="button"
              onClick={() =>
                save(
                  active
                    ? { clear_verdict: true }
                    : { verdict: choice.value },
                )
              }
              className={
                "rounded-full border px-3 py-1 text-sm transition-colors " +
                (active
                  ? "border-[var(--color-ink)] bg-[var(--color-ink)] text-[var(--color-paper)]"
                  : "border-[var(--color-rule)] text-[var(--color-ink-soft)] hover:border-[var(--color-ink-soft)]")
              }
              aria-pressed={active}
            >
              {choice.label}
            </button>
          );
        })}
      </div>

      {/* The model's answer stays visible. Hiding it once someone overrules it
          would lose the comparison that says whether the thesis is working. */}
      <p className="mb-3 text-[0.8125rem] text-[var(--color-ink-faint)]">
        {chosen
          ? chosen === candidate.verdict
            ? `You agreed with the filter. Click ${
                CHOICES.find((c) => c.value === chosen)?.label
              } again to undo.`
            : `The filter said ${candidate.verdict.replace("_", " ")}. Yours wins.`
          : `The filter said ${candidate.verdict.replace("_", " ")}. Pick one to override it.`}
      </p>

      <textarea
        value={note}
        onChange={(event) => {
          setNote(event.target.value);
          setState("idle");
        }}
        rows={3}
        placeholder="Why? Anything the filing can't tell you — who you spoke to, what put you off, what would change your mind."
        className="w-full resize-y rounded border border-[var(--color-rule)] bg-transparent p-2 text-sm text-[var(--color-ink)] placeholder:text-[var(--color-ink-faint)] focus:border-[var(--color-ink-soft)] focus:outline-none"
      />

      <div className="mt-2 flex items-center gap-3">
        <button
          type="button"
          onClick={() => save({ note })}
          disabled={!dirty || state === "saving"}
          className="rounded border border-[var(--color-rule)] px-3 py-1 text-sm text-[var(--color-ink-soft)] transition-colors hover:border-[var(--color-ink-soft)] disabled:opacity-40"
        >
          {state === "saving" ? "Saving" : "Save note"}
        </button>

        <span className="text-[0.8125rem] text-[var(--color-ink-faint)]">
          {state === "failed"
            ? "Didn't save — try again."
            : state === "done"
              ? "Saved."
              : candidate.decided_at
                ? `Last edited ${candidate.decided_at.slice(0, 10)}`
                : ""}
        </span>
      </div>
    </section>
  );
}
