"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { VerdictKey } from "@/components/VerdictKey";

/**
 * The criteria page as a visitor sees it: their own domains, and a way to add one.
 *
 * A domain written here is judged at once against companies the radar already
 * knows, and from then on appears in this visitor's dropdown and list like any
 * other. It is theirs alone — kept against an anonymous id in this browser —
 * and never reaches the owner's record.
 */

type VisitorDomain = {
  domain: string;
  theme: string;
  include: string[];
  exclude: string[];
  min_amount?: number | null;
  judged: number;
  fits: number;
  maybe: number;
  left: number;
};

type TryResult = {
  theme: string;
  judged: number;
  fits: number;
  maybe: number;
  unknown: number;
  no_fit: number;
  left: number;
  problems: string[];
};

async function errorFrom(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;

  // Our own refusals carry `errors`; a malformed form comes back as FastAPI's
  // list of validation problems.
  return (
    detail?.errors?.[0] ??
    (Array.isArray(detail) ? String(detail[0]?.msg ?? "").replace(/^Value error, /, "") : null) ??
    `Something went wrong (${response.status}).`
  );
}

const lines = (value: string) =>
  value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

const box =
  "w-full rounded border border-[var(--color-rule)] bg-[var(--color-paper)] px-3 py-2 text-sm text-[var(--color-ink)] focus:border-[var(--color-ink)] focus:outline-none";

export function VisitorCriteria() {
  const [domains, setDomains] = useState<VisitorDomain[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<TryResult | null>(null);

  const [name, setName] = useState("");
  const [include, setInclude] = useState("");
  const [exclude, setExclude] = useState("");
  const [minimum, setMinimum] = useState("");

  const load = useCallback(async () => {
    const response = await fetch("/api/visitor/domains", { cache: "no-store" }).catch(() => null);

    setDomains(response?.ok ? ((await response.json()) as VisitorDomain[]) : []);
  }, []);

  useEffect(() => {
    // Reading is the effect's job; the state it sets comes after the request.
    let cancelled = false;

    fetch("/api/visitor/domains", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : []))
      .then((found: VisitorDomain[]) => {
        if (!cancelled) setDomains(found);
      })
      .catch(() => {
        if (!cancelled) setDomains([]);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function act(label: string, request: () => Promise<Response>, after?: () => void) {
    setBusy(label);
    setError(null);
    setLast(null);

    try {
      const response = await request();

      if (!response.ok) {
        setError(await errorFrom(response));
        return;
      }

      const body = await response.json();

      if (body && typeof body === "object" && "judged" in body) setLast(body as TryResult);

      after?.();
      await load();
    } catch {
      setError("Could not reach the server.");
    } finally {
      setBusy(null);
    }
  }

  function create() {
    const wanted = lines(include);

    if (!name.trim() || wanted.length === 0) {
      setError("Give it a name and at least one thing to look for.");
      return;
    }

    void act(
      "create",
      () =>
        fetch("/api/visitor/domains", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            domain: name.trim(),
            include: wanted,
            exclude: lines(exclude),
            min_amount: minimum ? Math.round(Number(minimum) * 1_000_000) : null,
          }),
        }),
      () => {
        setName("");
        setInclude("");
        setExclude("");
        setMinimum("");
      },
    );
  }

  const path = (theme: string) => `/api/visitor/domains/${encodeURIComponent(theme)}`;

  return (
    <div className="space-y-10">
      <section>
        <p className="max-w-2xl text-sm leading-relaxed text-[var(--color-ink-soft)]">
          Write what you&apos;re looking for, and the radar judges companies it already
          knows against it — about 15 at a time, in roughly half a minute. Your domains
          appear in the dropdown on the companies page, and only you can see them, in
          this browser.
        </p>

        <div className="mt-4">
          <VerdictKey />
        </div>
      </section>

      {last && (
        <section className="rounded border border-[var(--color-rule)] bg-[var(--color-paper-raised)] p-4 text-sm">
          {last.judged === 0 && last.problems.length > 0 ? (
            <p className="text-[var(--color-maybe)]">
              None of the companies could be judged just now — nothing was ruled in or
              out. Please try again in a few minutes.
            </p>
          ) : last.judged === 0 ? (
            <p>No more companies match these criteria.</p>
          ) : (
            <>
              <p className="tabular">
                Judged {last.judged}: {last.fits} fit · {last.maybe} maybe · {last.unknown}{" "}
                unknown · {last.no_fit} no fit
                {last.left > 0 && <> — {last.left} more to judge</>}.
              </p>
              <Link
                href={`/?theme=${encodeURIComponent(last.theme)}`}
                className="mt-2 inline-block underline underline-offset-2"
              >
                See them
              </Link>
            </>
          )}
        </section>
      )}

      {error && <p className="text-sm text-[var(--color-maybe)]">{error}</p>}

      <section>
        <h2 className="font-display text-[1.125rem]">Your domains</h2>

        {domains === null ? (
          <p className="label mt-3">Loading</p>
        ) : domains.length === 0 ? (
          <p className="mt-2 text-sm text-[var(--color-ink-faint)]">None yet — add one below.</p>
        ) : (
          <div className="mt-4 space-y-6">
            {domains.map((item) => (
              <article key={item.theme} className="border-t-2 border-[var(--color-ink)] pt-3">
                <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
                  <h3 className="font-display text-[1.0625rem]">{item.domain}</h3>

                  <div className="flex items-baseline gap-4 text-[0.8125rem]">
                    <Link
                      href={`/?theme=${encodeURIComponent(item.theme)}`}
                      className="text-[var(--color-ink-faint)] hover:text-[var(--color-ink)]"
                    >
                      See companies
                    </Link>
                    {item.left > 0 && (
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() =>
                          void act(item.theme, () => fetch(`${path(item.theme)}/more`, { method: "POST" }))
                        }
                        className="text-[var(--color-ink-faint)] hover:text-[var(--color-ink)] disabled:opacity-50"
                      >
                        {busy === item.theme ? "Judging…" : "Judge 15 more"}
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() =>
                        void act(`delete-${item.theme}`, () => fetch(path(item.theme), { method: "DELETE" }))
                      }
                      className="text-[var(--color-ink-faint)] hover:text-[var(--color-nofit)] disabled:opacity-50"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                <p className="tabular mt-1 text-[0.75rem] text-[var(--color-ink-faint)]">
                  {item.judged} judged · {item.fits} fit · {item.maybe} maybe
                  {item.left > 0 ? ` · ${item.left} more to judge` : ""}
                </p>

                <ul className="mt-2 space-y-0.5 text-sm">
                  {item.include.map((line) => (
                    <li key={`+${line}`}>
                      <span className="text-[var(--color-fits)]">+</span> {line}
                    </li>
                  ))}
                  {item.exclude.map((line) => (
                    <li key={`-${line}`} className="text-[var(--color-ink-soft)]">
                      <span className="text-[var(--color-ink-faint)]">−</span> {line}
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="border-t border-[var(--color-rule)] pt-6">
        <h2 className="font-display text-[1.125rem]">Add a domain</h2>

        <div className="mt-4 max-w-xl space-y-4">
          <label className="block text-sm text-[var(--color-ink-soft)]">
            Name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={30}
              placeholder="Robotics"
              className={`${box} mt-1`}
            />
          </label>

          <label className="block text-sm text-[var(--color-ink-soft)]">
            What you&apos;re looking for <span className="text-[var(--color-ink-faint)]">— one per line</span>
            <textarea
              value={include}
              onChange={(event) => setInclude(event.target.value)}
              rows={4}
              placeholder={"industrial robots and automation\nAI for factory inspection"}
              className={`${box} mt-1 resize-y`}
            />
          </label>

          <label className="block text-sm text-[var(--color-ink-soft)]">
            What to rule out <span className="text-[var(--color-ink-faint)]">— optional, one per line</span>
            <textarea
              value={exclude}
              onChange={(event) => setExclude(event.target.value)}
              rows={3}
              placeholder={"consumer gadgets\nconsultancies"}
              className={`${box} mt-1 resize-y`}
            />
          </label>

          <label className="block text-sm text-[var(--color-ink-soft)]">
            Smallest raise <span className="text-[var(--color-ink-faint)]">— in millions, optional</span>
            <input
              type="number"
              min="0"
              step="0.1"
              value={minimum}
              onChange={(event) => setMinimum(event.target.value)}
              placeholder="any"
              className={`${box} tabular mt-1 max-w-[10rem]`}
            />
          </label>

          <button
            type="button"
            disabled={busy !== null}
            onClick={create}
            className="rounded border border-[var(--color-ink)] bg-[var(--color-ink)] px-4 py-2 text-sm text-[var(--color-paper)] transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {busy === "create" ? "Judging… about half a minute" : "Create and judge"}
          </button>
        </div>
      </section>
    </div>
  );
}
