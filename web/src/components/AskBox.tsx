"use client";

import { useState } from "react";

import type { ChatAnswer } from "@/lib/api";

const EXAMPLES = [
  "which ones fitted?",
  "why did we pass on the device companies?",
  "which maybes are worth another look?",
];

export function AskBox({ theme }: { theme: string | null }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<ChatAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);

  async function ask(text: string) {
    const cleaned = text.trim();

    if (!cleaned || asking) return;

    setAsking(true);
    setError(null);
    setAnswer(null);

    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: cleaned, theme }),
    });

    setAsking(false);

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const errors = body?.detail?.errors;

      setError(
        Array.isArray(errors)
          ? errors.join(" ")
          : `Could not answer (${response.status}).`,
      );

      return;
    }

    setAnswer((await response.json()) as ChatAnswer);
  }

  return (
    <section className="sticky bottom-0 border-t border-[var(--color-rule)] bg-[color-mix(in_srgb,var(--color-paper)_92%,transparent)] backdrop-blur-sm">
      <div className="mx-auto max-w-3xl px-8 py-5">
        {answer && (
          <div className="mb-4 border-l-2 border-[var(--color-ink)] pl-4">
            <p className="font-display text-[0.9375rem] leading-relaxed whitespace-pre-wrap text-[var(--color-ink)]">
              {answer.answer}
            </p>
            <p className="label mt-2">
              from {answer.considered} recorded judgement
              {answer.considered === 1 ? "" : "s"}
            </p>
          </div>
        )}

        {error && (
          <p className="mb-3 border-l-2 border-[var(--color-maybe)] pl-4 text-sm text-[var(--color-maybe)]">
            {error}
          </p>
        )}

        <form
          onSubmit={(event) => {
            event.preventDefault();
            void ask(question);
          }}
          className="flex items-baseline gap-3"
        >
          <input
            type="text"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask about what has already been judged"
            maxLength={500}
            className="field flex-1 placeholder:text-[var(--color-ink-faint)]"
          />

          <button
            type="submit"
            disabled={asking || !question.trim()}
            className="shrink-0 border-b border-[var(--color-ink)] pb-0.5 text-[0.6875rem] tracking-[0.08em] uppercase text-[var(--color-ink)] transition-opacity disabled:border-transparent disabled:opacity-30"
          >
            {asking ? "Asking" : "Ask"}
          </button>
        </form>

        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => {
                setQuestion(example);
                void ask(example);
              }}
              className="text-[0.75rem] text-[var(--color-ink-faint)] transition-colors hover:text-[var(--color-ink)]"
            >
              {example}
            </button>
          ))}
        </div>

        <p className="mt-3 text-[0.6875rem] leading-relaxed text-[var(--color-ink-faint)]">
          Answers draw only on judgements already recorded. This cannot search or
          research anything new.
        </p>
      </div>
    </section>
  );
}
