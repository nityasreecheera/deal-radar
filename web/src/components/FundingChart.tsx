"use client";

import { useState } from "react";

import { formatAmount, type FundingRound } from "@/lib/api";

/**
 * Round size over time.
 *
 * A line, because the question is a trajectory — are the raises getting bigger?
 * Markers sit on every actual filing so the discrete events stay visible; the
 * line carries direction, the dots carry "this is a real data point".
 *
 * Two decisions that matter more than they look:
 *
 * The value plotted is the round's *target*, not the amount sold. A round that
 * has just opened has sold nothing, and plotting that would draw the line
 * collapsing to zero — an artifact of timing, not a fall in the company's
 * fortunes.
 *
 * Amendments are excluded. An amendment restates a round that is already on the
 * chart, so drawing it would invent a raise that never happened. They stay in
 * the list underneath, where they are labelled as what they are.
 *
 * Monochrome: one series, so there is nothing for colour to identify.
 */

const HEIGHT = 110;
const PAD_X = 12;
const PAD_TOP = 14;
const LABEL_SPACE = 22;
const MIN_WIDTH = 220;

export function FundingChart({ rounds }: { rounds: FundingRound[] }) {
  const [hovered, setHovered] = useState<number | null>(null);

  const points = rounds.filter((round) => {
    if (round.is_amendment) return false;

    // A round with no amount disclosed is not a round of zero. Plotting it as
    // one draws the line collapsing to the floor, which reads as the company
    // falling apart — 1104Health raised $1M in 2023 and filed an undisclosed
    // amount in 2026, and that would have rendered as a crash. Leave it out of
    // the line; the list underneath still shows the filing.
    return (round.offering_amount ?? round.amount_sold ?? 0) > 0;
  });

  // One point is not a trend. The caller says "first raise" in words instead.
  if (points.length < 2) return null;

  const values = points.map(
    (round) => round.offering_amount ?? round.amount_sold ?? 0,
  );
  const ceiling = Math.max(...values, 1);

  const width = Math.max(MIN_WIDTH, points.length * 90);
  const plotWidth = width - PAD_X * 2;
  const plotHeight = HEIGHT - PAD_TOP;

  const coords = values.map((value, index) => ({
    x: PAD_X + (plotWidth * index) / (points.length - 1),
    y: PAD_TOP + plotHeight - (value / ceiling) * plotHeight,
  }));

  const path = coords
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");

  const active = hovered === null ? null : points[hovered];

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${width} ${HEIGHT + LABEL_SPACE}`}
        width={width}
        height={HEIGHT + LABEL_SPACE}
        role="img"
        aria-label={`Round size across ${points.length} raises`}
        className="overflow-visible"
      >
        {/* Baseline only. A full grid would be more furniture than data for
            three points. */}
        <line
          x1={0}
          y1={HEIGHT}
          x2={width}
          y2={HEIGHT}
          stroke="var(--color-rule)"
          strokeWidth={1}
        />

        <path
          d={path}
          fill="none"
          stroke="var(--color-ink)"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {coords.map((point, index) => {
          const round = points[index];
          const isActive = hovered === index;

          return (
            <g
              key={round.accession}
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
            >
              {/* Hit target far larger than the dot. */}
              <rect
                x={point.x - width / (points.length * 2)}
                y={0}
                width={width / points.length}
                height={HEIGHT + LABEL_SPACE}
                fill="transparent"
              />

              {/* A ring in the surface colour so the marker stays legible
                  where the line passes behind it. */}
              <circle
                cx={point.x}
                cy={point.y}
                r={isActive ? 6 : 4.5}
                fill="var(--color-ink)"
                stroke="var(--color-paper)"
                strokeWidth={2}
                className="transition-all"
              />

              <text
                x={point.x}
                y={HEIGHT + 15}
                textAnchor="middle"
                fontSize={10}
                fill="var(--color-ink-faint)"
              >
                {round.filed_date.slice(0, 4)}
              </text>
            </g>
          );
        })}

        {/* Only the first and last are labelled. A number on every point is
            noise when the caption gives the exact figure on hover. */}
        {[0, coords.length - 1].map((index) => (
          <text
            key={index}
            x={coords[index].x}
            y={coords[index].y - 11}
            textAnchor={index === 0 ? "start" : "end"}
            fontSize={10}
            fill="var(--color-ink-soft)"
          >
            {formatAmount(values[index])}
          </text>
        ))}
      </svg>

      <figcaption className="mt-1 min-h-[1.25rem] text-[0.8125rem] text-[var(--color-ink-soft)]">
        {active ? (
          <>
            <span className="tabular">{active.filed_date}</span>
            {" · raising "}
            <span className="tabular">
              {formatAmount(active.offering_amount)}
            </span>
            {active.amount_sold != null && (
              <span className="text-[var(--color-ink-faint)]">
                {" · "}
                <span className="tabular">
                  {formatAmount(active.amount_sold)}
                </span>{" "}
                sold
              </span>
            )}
          </>
        ) : (
          <span className="text-[var(--color-ink-faint)]">
            Round size over time. Hover a point for detail.
          </span>
        )}
      </figcaption>
    </figure>
  );
}
