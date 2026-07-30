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
    <section className="sticky bottom-0 border-t border-slate-200 bg-white/95 px-6 py-4 backdrop-blur">
      <div className="mx-auto max-w-4xl">
        {answer && (
          <div className="mb-3 rounded-lg bg-slate-100 px-4 py-3 text-sm">
            <p className="whitespace-pre-wrap">{answer.answer}</p>
            <p className="mt-2 text-xs text-slate-500">
              From {answer.considered} recorded judgement
              {answer.considered === 1 ? "" : "s"}. Nothing else was consulted.
            </p>
          </div>
        )}

        {error && (
          <div className="mb-3 rounded-lg border border-rose-300 bg-rose-50 px-4 py-2 text-sm text-rose-800">
            {error}
          </div>
        )}

        <form
          onSubmit={(event) => {
            event.preventDefault();
            void ask(question);
          }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask about what has already been judged…"
            maxLength={500}
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />

          <button
            type="submit"
            disabled={asking || !question.trim()}
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-40"
          >
            {asking ? "Asking…" : "Ask"}
          </button>
        </form>

        <div className="mt-2 flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => {
                setQuestion(example);
                void ask(example);
              }}
              className="rounded-full border border-slate-300 px-2.5 py-0.5 text-xs text-slate-600 hover:bg-slate-100"
            >
              {example}
            </button>
          ))}
        </div>

        <p className="mt-2 text-xs text-slate-400">
          Answers come only from stored judgements. It cannot search the web or
          research anything new — ask the agent for that.
        </p>
      </div>
    </section>
  );
}
