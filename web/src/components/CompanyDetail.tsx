"use client";

import { FundingChart } from "@/components/FundingChart";
import { formatAmount, type Detail } from "@/lib/api";

/**
 * The parts of a company that only exist once you look across filings.
 *
 * Handed the detail rather than fetching it, because the contact panel needs the
 * same object and two components fetching one endpoint is two requests to draw
 * one page.
 */
export function CompanyDetail({ detail }: { detail: Detail }) {
  const rounds = detail.rounds ?? [];
  const people = detail.shared_people ?? [];
  const percent = detail.progress_percent;

  return (
    <div className="space-y-6">
      {percent !== null && percent !== undefined && (
        <section>
          <h3 className="label mb-2">This round</h3>

          <div className="max-w-sm">
            <div className="h-[3px] w-full bg-[var(--color-rule)]">
              <div
                className="h-full bg-[var(--color-ink)]"
                style={{ width: `${Math.min(percent, 100)}%` }}
              />
            </div>

            <p className="mt-2 text-sm">
              <span className="tabular">
                {formatAmount(detail.candidate.amount_sold)}
              </span>{" "}
              of{" "}
              <span className="tabular">
                {formatAmount(detail.candidate.offering_amount)}
              </span>{" "}
              <span className="text-[var(--color-ink-faint)]">
                · {detail.progress_note}
              </span>
            </p>

            {/* How old the deal actually is. A round filed a year after it
                opened looks identical to a fresh one in the list, and the
                difference decides whether there is anything left to join. */}
            {detail.candidate.first_sale_date && (
              <p className="mt-1 text-sm text-[var(--color-ink-soft)]">
                First money in{" "}
                <span className="tabular">
                  {detail.candidate.first_sale_date}
                </span>
                <span className="text-[var(--color-ink-faint)]">
                  {" · "}
                  {detail.age_note}
                </span>
              </p>
            )}

            {detail.minimum_note && (
              <p className="mt-1 text-sm text-[var(--color-ink-faint)]">
                {detail.minimum_note}
              </p>
            )}
          </div>
        </section>
      )}

      {/* How this company sits among the ones like it. Above the funding
          history because it frames everything below: the fifth of something is
          read differently from the first. */}
      {detail.category_note && (
        <section>
          <h3 className="label mb-2">Among the ones like it</h3>

          <p className="text-sm text-[var(--color-ink-soft)]">
            {detail.category_note}
          </p>
        </section>
      )}

      {rounds.length > 0 && (
        <section>
          <h3 className="label mb-2">Funding history</h3>

          <p className="mb-3 text-sm text-[var(--color-ink-soft)]">
            {detail.funding_summary}
          </p>

          <div className="mb-4">
            <FundingChart rounds={rounds} />
          </div>

          {/* The same numbers as text. A chart is not readable by everything,
              and exact figures are easier to take from a list than a bar. */}
          <ol className="space-y-1.5">
            {rounds.map((round) => (
              <li
                key={round.accession}
                className="flex items-baseline gap-4 text-sm"
              >
                <span className="tabular w-24 shrink-0 text-[var(--color-ink-faint)]">
                  {round.filed_date}
                </span>

                <span className="tabular w-20 shrink-0">
                  {formatAmount(round.offering_amount)}
                </span>

                <span className="text-[var(--color-ink-faint)]">
                  {round.is_amendment
                    ? "amended"
                    : round.amount_sold
                      ? `${formatAmount(round.amount_sold)} sold`
                      : "nothing sold yet"}
                </span>
              </li>
            ))}
          </ol>

          {detail.is_first_raise && (
            <p className="mt-2 text-sm text-[var(--color-fits)]">
              First money in.
            </p>
          )}
        </section>
      )}

      {people.length > 0 && (
        <section>
          <h3 className="label mb-2">Also appears elsewhere</h3>

          <ul className="space-y-1.5">
            {people.map((person) => (
              <li key={person.full_name} className="text-sm">
                <span className="font-display text-[0.9375rem]">
                  {person.full_name}
                </span>
                <span className="text-[var(--color-ink-faint)]">
                  {" is also on "}
                  {(person.other_companies ?? []).join(", ")}
                </span>
              </li>
            ))}
          </ul>

          <p className="mt-2 text-[0.75rem] text-[var(--color-ink-faint)]">
            Only covers companies this radar has already seen. EDGAR does not
            index the names on a filing, so this cannot search all of it.
          </p>
        </section>
      )}
    </div>
  );
}
