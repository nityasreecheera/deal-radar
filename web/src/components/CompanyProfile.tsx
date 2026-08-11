"use client";

import { CompanyDetail } from "@/components/CompanyDetail";
import {
  filingUrl,
  formatAmount,
  type Candidate,
} from "@/lib/api";

/**
 * Everything known about one company.
 *
 * Lifted out of the list row when companies got their own page. The list is for
 * scanning; this is for deciding, and the two want different amounts of room.
 */
export function CompanyProfile({ candidate }: { candidate: Candidate }) {
  // Optional in the generated schema because the Pydantic field has a
  // default_factory, though the API always sends it.
  const people = candidate.people ?? [];
  const filing = filingUrl(candidate);

  return (
    <div className="space-y-6">
      {candidate.summary && (
        <p className="font-display max-w-2xl text-[1.0625rem] leading-relaxed text-[var(--color-ink)]">
          {candidate.summary}
        </p>
      )}

      <p className="max-w-2xl text-[0.9375rem] leading-relaxed text-[var(--color-ink-soft)]">
        {candidate.reason}
      </p>

      {candidate.website && (
        <a
          href={candidate.website}
          target="_blank"
          rel="noreferrer"
          className="inline-block border-b border-[var(--color-ink-faint)] pb-0.5 text-sm text-[var(--color-ink)] transition-colors hover:border-[var(--color-ink)]"
        >
          {candidate.website.replace(/^https?:\/\//, "")}
        </a>
      )}

      <section>
        <h3 className="label mb-2">Officers and directors</h3>

        {people.length === 0 ? (
          <p className="text-sm text-[var(--color-ink-faint)]">
            None named on the filing.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {people.map((person) => (
              <li
                key={`${person.first_name}-${person.last_name}`}
                className="text-sm"
              >
                <span className="font-display text-[0.9375rem]">
                  {[person.first_name, person.last_name]
                    .filter(Boolean)
                    .join(" ")}
                </span>
                {(person.relationships ?? []).length > 0 && (
                  <span className="text-[var(--color-ink-soft)]">
                    {"  "}
                    {(person.relationships ?? []).join(", ")}
                  </span>
                )}
                {person.city && (
                  <span className="text-[var(--color-ink-faint)]">
                    {"  ·  "}
                    {person.city}
                    {person.state ? `, ${person.state}` : ""}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <dl className="grid max-w-2xl grid-cols-2 gap-x-10 gap-y-3 sm:grid-cols-3">
        <Fact label="Raising" value={formatAmount(candidate.offering_amount)} />
        <Fact label="Sold so far" value={formatAmount(candidate.amount_sold)} />
        <Fact
          label="Investors"
          value={
            candidate.investor_count == null
              ? "unknown"
              : String(candidate.investor_count)
          }
        />
        <Fact
          label="Incorporated"
          value={
            candidate.incorporated ? String(candidate.incorporated) : "unknown"
          }
        />
        <Fact label="Entity" value={candidate.entity_type ?? "unknown"} />
        <Fact label="Registered" value={candidate.jurisdiction ?? "unknown"} />
      </dl>

      {candidate.description && (
        <p className="max-w-2xl border-l border-[var(--color-rule)] pl-4 text-[0.8125rem] leading-relaxed text-[var(--color-ink-faint)] italic">
          {candidate.description}
        </p>
      )}

      <CompanyDetail accession={candidate.accession} />

      <div className="flex flex-wrap items-center gap-5 text-[0.75rem] text-[var(--color-ink-faint)]">
        {candidate.industry_group && <span>{candidate.industry_group}</span>}

        {filing && (
          <a
            href={filing}
            target="_blank"
            rel="noreferrer"
            className="border-b border-[var(--color-rule)] pb-0.5 transition-colors hover:border-[var(--color-ink-faint)] hover:text-[var(--color-ink-soft)]"
          >
            the filing on SEC.gov
          </a>
        )}
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="tabular mt-0.5 text-sm text-[var(--color-ink)]">{value}</dd>
    </div>
  );
}
