"use client";

import { useState } from "react";

import { formatAmount, type FundingRound } from "@/lib/api";

/**
 * Raises over time.
 *
 * Bars, not a line. A line implies the company sat at some value between rounds,
 * and it did not — a raise is a discrete event. Time runs left to right so the
 * shape reads as a sequence rather than a ranking.
 *
 * Each bar is one round. Full height is what they asked for; the filled part is
 * what actually sold. That puts "how big" and "how much of it closed" in one
 * mark instead of two charts.
 *
 * Monochrome on purpose. There are no categories here, only a portion of a
 * whole, so there is nothing for colour to identify and nothing to confuse.
 */

const HEIGHT = 96;
const BAR_WIDTH = 44;
const GAP = 10;
const LABEL_SPACE = 20;

export function FundingChart({ rounds }: { rounds: FundingRound[] }) {
  const [hovered, setHovered] = useState<number | null>(null);

  // One bar is not a chart. The caller says "first raise" in words instead.
  if (rounds.length < 2) return null;

  const amounts = rounds.map((r) =>
    Math.max(r.offering_amount ?? 0, r.amount_sold ?? 0),
  );
  const ceiling = Math.max(...amounts, 1);

  const width = rounds.length * BAR_WIDTH + (rounds.length - 1) * GAP;
  const active = hovered === null ? null : rounds[hovered];

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${width} ${HEIGHT + LABEL_SPACE}`}
        width={width}
        height={HEIGHT + LABEL_SPACE}
        role="img"
        aria-label={`Funding history: ${rounds.length} filings`}
        className="overflow-visible"
      >
        {/* Baseline. Recessive on purpose — it orients, it does not decorate. */}
        <line
          x1={0}
          y1={HEIGHT}
          x2={width}
          y2={HEIGHT}
          stroke="var(--color-rule)"
          strokeWidth={1}
        />

        {rounds.map((round, index) => {
          const target = round.offering_amount ?? 0;
          const sold = round.amount_sold ?? 0;

          const x = index * (BAR_WIDTH + GAP);
          const targetHeight = (target / ceiling) * HEIGHT;
          const soldHeight = (sold / ceiling) * HEIGHT;

          const dim = hovered !== null && hovered !== index;

          return (
            <g
              key={round.accession}
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
              opacity={dim ? 0.4 : 1}
              className="transition-opacity"
            >
              {/* Generous hit target, larger than the mark itself. */}
              <rect
                x={x - GAP / 2}
                y={0}
                width={BAR_WIDTH + GAP}
                height={HEIGHT + LABEL_SPACE}
                fill="transparent"
              />

              {/* What they asked for. */}
              <rect
                x={x}
                y={HEIGHT - targetHeight}
                width={BAR_WIDTH}
                height={Math.max(targetHeight, 1)}
                rx={3}
                fill="var(--color-rule)"
              />

              {/* What actually sold, anchored to the baseline. */}
              {soldHeight > 0 && (
                <rect
                  x={x}
                  y={HEIGHT - soldHeight}
                  width={BAR_WIDTH}
                  height={Math.max(soldHeight, 2)}
                  rx={3}
                  fill={
                    round.is_amendment
                      ? "var(--color-ink-faint)"
                      : "var(--color-ink)"
                  }
                />
              )}

              <text
                x={x + BAR_WIDTH / 2}
                y={HEIGHT + 14}
                textAnchor="middle"
                fontSize={10}
                fill="var(--color-ink-faint)"
              >
                {round.filed_date.slice(0, 4)}
              </text>
            </g>
          );
        })}
      </svg>

      {/* A caption rather than a floating tooltip. The chart is small, the
          detail is long, and a box covering two of four bars helps nobody. */}
      <figcaption className="mt-2 min-h-[1.25rem] text-[0.8125rem] text-[var(--color-ink-soft)]">
        {active ? (
          <>
            <span className="tabular">{active.filed_date}</span>
            {" · "}
            <span className="tabular">
              {formatAmount(active.amount_sold)}
            </span>{" "}
            sold of{" "}
            <span className="tabular">
              {formatAmount(active.offering_amount)}
            </span>
            {active.is_amendment && (
              <span className="text-[var(--color-ink-faint)]">
                {" · amends an earlier filing"}
              </span>
            )}
          </>
        ) : (
          <span className="text-[var(--color-ink-faint)]">
            Filled shows what sold. Hover a bar for detail.
          </span>
        )}
      </figcaption>
    </figure>
  );
}
