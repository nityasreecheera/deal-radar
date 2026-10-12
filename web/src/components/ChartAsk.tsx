"use client";

import { useState } from "react";

import { Chart, type ChartAnswer } from "@/components/Chart";

/**
 * Ask for a chart in plain English.
 *
 * Owner and visitors alike. The answer is drawn from what the asker may read —
 * the API decides that, not this box — so a visitor's chart never includes a
 * private domain or the owner's own verdicts.
 */

const EXAMPLES = [
  "Top 10 companies by amount being raised",
  "How many companies by verdict",
  "Total being raised by month",
  "Fits by raise size",
  "Companies by state",
];

type Asked = { question: string; answer: ChartAnswer };

async function errorFrom(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);

  return (
    body?.detail?.errors?.[0] ??
    (Array.isArray(body?.detail) ? "Ask in a few words — up to 300 characters." : null) ??
    `Something went wrong (${response.status}).`
  );
}

export function ChartAsk() {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Asked[]>([]);

  async function ask(text: string) {
    const wanted = text.trim();

    if (!wanted) return;

    setBusy(true);
    setError(null);

    try {
      const response = await fetch("/api/charts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: wanted }),
      });

      if (!response.ok) {
        setError(await errorFrom(response));
        return;
      }

      const answer = (await response.json()) as ChartAnswer;

      // Newest first, and only the last few: a page of twenty charts is a page
      // nobody reads.
      setHistory((current) => [{ question: wanted, answer }, ...current].slice(0, 4));
      setQuestion("");
    } catch {
      setError("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2 className="font-display mb-1 text-[1.125rem]">Ask for a chart</h2>
      <p className="mb-3 max-w-2xl text-[0.8125rem] text-[var(--color-ink-faint)]">
        Compare companies (&ldquo;Cornelis Networks vs DriveNets&rdquo;), break the numbers down
        (&ldquo;raises by month in AI tools&rdquo;), or rank them (&ldquo;top 10 fits by
        size&rdquo;).
      </p>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
        className="flex flex-wrap gap-2"
      >
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          maxLength={300}
          placeholder="What do you want to see?"
          className="field min-w-0 flex-1 basis-64"
        />
        <button
          type="submit"
          disabled={busy || !question.trim()}
          className="rounded border border-[var(--color-ink)] bg-[var(--color-ink)] px-4 py-2 text-sm text-[var(--color-paper)] transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "Drawing…" : "Chart it"}
        </button>
      </form>

      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            disabled={busy}
            onClick={() => void ask(example)}
            className="text-[0.75rem] text-[var(--color-ink-faint)] underline underline-offset-2 hover:text-[var(--color-ink)] disabled:opacity-50"
          >
            {example}
          </button>
        ))}
      </div>

      {error && <p className="mt-3 text-sm text-[var(--color-maybe)]">{error}</p>}

      <div className="mt-5 space-y-5">
        {history.map((item, index) => (
          <div key={`${item.question}-${index}`}>
            <p className="mb-1.5 text-[0.75rem] text-[var(--color-ink-faint)]">&ldquo;{item.question}&rdquo;</p>
            <Chart answer={item.answer} />
          </div>
        ))}
      </div>
    </section>
  );
}
