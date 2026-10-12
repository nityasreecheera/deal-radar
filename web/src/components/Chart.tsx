"use client";

import { useState } from "react";

/**
 * Draws a ChartAnswer from /api/charts: ranked bars, a line over months, or
 * companies side by side. Plain SVG, no library.
 *
 * Colour is assigned by job and validated against this site's paper surface
 * (dataviz validator, light mode, surface #faf8f5):
 *   - several series:  reference categorical order, blue / orange / aqua / yellow
 *   - verdicts:        fits aqua, maybe yellow, unknown blue, no fit orange — the
 *                      site's own fits-green and maybe-amber failed as a pair
 *                      (normal-vision ΔE 12), so charts do not reuse them
 *   - one series:      ink; one series needs no hue and no legend
 * Aqua and yellow sit below 3:1 on paper, so every chart has visible labels and a
 * table view — the relief the validator requires.
 */

export type ChartAnswer = {
  title: string;
  subtitle?: string;
  form: "bar" | "line" | "grouped" | "none";
  unit: "count" | "usd" | "mixed";
  categories: string[];
  series: { name: string; values: (number | null)[] }[];
  colour_by: "series" | "verdict" | "single";
  columns: string[];
  rows: string[][];
  note?: string | null;
};

const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];
const VERDICT: Record<string, string> = {
  Fits: "#1baf7a",
  Maybe: "#eda100",
  Unknown: "#2a78d6",
  "No fit": "#eb6834",
};
const INK = "#4a4340";
const GRID = "#e6e0d8";
const MUTED = "#8a807b";

export function format(value: number | null | undefined, unit: ChartAnswer["unit"]): string {
  if (value === null || value === undefined) return "—";

  if (unit !== "usd") return value.toLocaleString();

  // One decimal where it says something, none on a round axis tick.
  const short = (n: number) => (Number.isInteger(Math.round(n * 10) / 10) ? n.toFixed(0) : n.toFixed(1));

  if (value >= 1e9) return `$${short(value / 1e9)}B`;
  if (value >= 1e6) return `$${short(value / 1e6)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(0)}K`;

  return `$${value.toFixed(0)}`;
}

/** A round top for the axis, so gridlines land on readable numbers. */
function niceMax(max: number): number {
  if (max <= 0) return 1;

  const step = 10 ** Math.floor(Math.log10(max));

  for (const multiple of [1, 2, 2.5, 5, 10]) {
    if (multiple * step >= max) return multiple * step;
  }

  return 10 * step;
}

/** A bar with its data end rounded and its baseline end square. */
function bar(x: number, y: number, width: number, height: number, horizontal: boolean): string {
  const r = Math.min(4, horizontal ? width / 2 : height / 2, horizontal ? height / 2 : width / 2);

  if (width <= 0 || height <= 0) return "";

  if (horizontal) {
    return `M${x},${y} H${x + width - r} Q${x + width},${y} ${x + width},${y + r} V${y + height - r} Q${x + width},${y + height} ${x + width - r},${y + height} H${x} Z`;
  }

  return `M${x},${y + height} V${y + r} Q${x},${y} ${x + r},${y} H${x + width - r} Q${x + width},${y} ${x + width},${y + r} V${y + height} Z`;
}

type Tip = { x: number; y: number; label: string; value: string } | null;

export function Chart({ answer }: { answer: ChartAnswer }) {
  const [asTable, setAsTable] = useState(false);
  const [tip, setTip] = useState<Tip>(null);

  const legend = answer.series.length > 1;

  return (
    <figure className="rounded border border-[var(--color-rule)] bg-[var(--color-paper-raised)] p-4">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span>
          <span className="font-display text-[1.0625rem]">{answer.title}</span>
          {answer.subtitle && (
            <span className="ml-2 text-[0.75rem] text-[var(--color-ink-faint)]">{answer.subtitle}</span>
          )}
        </span>
        <button
          type="button"
          onClick={() => setAsTable((value) => !value)}
          className="text-[0.75rem] text-[var(--color-ink-faint)] underline underline-offset-2 hover:text-[var(--color-ink)]"
        >
          {asTable ? "Show as chart" : "Show as table"}
        </button>
      </figcaption>

      {legend && !asTable && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[0.75rem] text-[var(--color-ink-soft)]">
          {answer.series.map((series, index) => (
            <span key={series.name} className="inline-flex items-center gap-1.5">
              <span
                aria-hidden
                className="inline-block h-2.5 w-2.5 rounded-sm"
                style={{ background: SERIES[index % SERIES.length] }}
              />
              {series.name}
            </span>
          ))}
        </div>
      )}

      <div className="relative mt-3">
        {asTable ? (
          <Table answer={answer} />
        ) : answer.form === "line" ? (
          <Line answer={answer} onTip={setTip} />
        ) : answer.form === "grouped" ? (
          <Grouped answer={answer} onTip={setTip} />
        ) : (
          <Bars answer={answer} onTip={setTip} />
        )}

        {tip && !asTable && (
          <div
            role="status"
            className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded border border-[var(--color-rule)] bg-[var(--color-paper)] px-2 py-1 text-[0.75rem] shadow-sm"
            style={{ left: tip.x, top: tip.y - 6 }}
          >
            <span className="text-[var(--color-ink-soft)]">{tip.label}</span>{" "}
            <span className="tabular text-[var(--color-ink)]">{tip.value}</span>
          </div>
        )}
      </div>

      {answer.note && <p className="mt-3 text-[0.75rem] text-[var(--color-ink-faint)]">{answer.note}</p>}
    </figure>
  );
}

/** Ranked horizontal bars: names stay readable however long they are. */
function Bars({ answer, onTip }: { answer: ChartAnswer; onTip: (tip: Tip) => void }) {
  const values = answer.series[0]?.values ?? [];
  const max = niceMax(Math.max(0, ...values.map((v) => v ?? 0)));
  const rowHeight = 26;
  const barHeight = 16;
  const labelWidth = 170;
  const valueWidth = 70;
  const width = 640;
  const plot = width - labelWidth - valueWidth;
  const height = answer.categories.length * rowHeight + 4;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={answer.title}>
      {answer.categories.map((category, index) => {
        const value = values[index] ?? 0;
        const length = (value / max) * plot;
        const y = index * rowHeight + 4;
        const fill =
          answer.colour_by === "verdict" ? (VERDICT[category] ?? INK) : INK;

        return (
          <g
            key={category}
            onMouseEnter={(event) => {
              const box = (event.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
              onTip({
                x: ((labelWidth + length / 2) / width) * box.width,
                y: (y / height) * box.height,
                label: category,
                value: format(values[index], answer.unit),
              });
            }}
            onMouseLeave={() => onTip(null)}
          >
            {/* Hit target the full row, bigger than the bar. */}
            <rect x={0} y={y - 4} width={width} height={rowHeight} fill="transparent" />
            <text
              x={labelWidth - 8}
              y={y + barHeight / 2}
              dominantBaseline="middle"
              textAnchor="end"
              fontSize={11}
              fill={INK}
            >
              {/* Cut short enough for capitals, the widest case, to fit. */}
              {category.length > 22 ? `${category.slice(0, 21)}…` : category}
            </text>
            <path d={bar(labelWidth, y, Math.max(length, 1), barHeight, true)} fill={fill} />
            <text
              x={labelWidth + length + 6}
              y={y + barHeight / 2}
              dominantBaseline="middle"
              fontSize={11}
              fill={MUTED}
              className="tabular"
            >
              {format(values[index], answer.unit)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Change over months: one 2px line, markers, labels on the first and last. */
function Line({ answer, onTip }: { answer: ChartAnswer; onTip: (tip: Tip) => void }) {
  const values = answer.series[0]?.values ?? [];
  const max = niceMax(Math.max(0, ...values.map((v) => v ?? 0)));
  const width = 640;
  const height = 220;
  const left = 64;
  const bottom = 28;
  const top = 12;
  const right = 16;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const step = values.length > 1 ? plotW / (values.length - 1) : 0;
  const point = (index: number) => ({
    x: left + index * step,
    y: top + plotH - ((values[index] ?? 0) / max) * plotH,
  });
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const path = values.map((_, i) => `${i === 0 ? "M" : "L"}${point(i).x},${point(i).y}`).join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={answer.title}>
      {ticks.map((tick) => {
        const y = top + plotH - (tick / max) * plotH;

        return (
          <g key={tick}>
            <line x1={left} x2={width - right} y1={y} y2={y} stroke={GRID} strokeWidth={1} />
            <text x={left - 8} y={y} textAnchor="end" dominantBaseline="middle" fontSize={10} fill={MUTED}>
              {format(tick, answer.unit)}
            </text>
          </g>
        );
      })}

      <path d={path} fill="none" stroke={INK} strokeWidth={2} strokeLinejoin="round" />

      {values.map((value, index) => {
        const { x, y } = point(index);
        const label = answer.categories[index];
        const edge = index === 0 || index === values.length - 1;

        return (
          <g
            key={label}
            onMouseEnter={(event) => {
              const box = (event.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
              onTip({ x: (x / width) * box.width, y: (y / height) * box.height, label, value: format(value, answer.unit) });
            }}
            onMouseLeave={() => onTip(null)}
          >
            <rect x={x - step / 2} y={top} width={Math.max(step, 16)} height={plotH} fill="transparent" />
            <circle cx={x} cy={y} r={4} fill={INK} stroke="#ffffff" strokeWidth={2} />
            {(edge || values.length <= 8) && (
              <text
                x={x}
                y={height - 8}
                // The first and last labels sit at the plot's edges; anchoring
                // them inward keeps them on the canvas.
                textAnchor={index === 0 ? "start" : index === values.length - 1 ? "end" : "middle"}
                fontSize={10}
                fill={MUTED}
              >
                {label}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/** Companies side by side: one group per measure, one bar per company. */
function Grouped({ answer, onTip }: { answer: ChartAnswer; onTip: (tip: Tip) => void }) {
  const all = answer.series.flatMap((s) => s.values.map((v) => v ?? 0));
  const max = niceMax(Math.max(0, ...all));
  const width = 640;
  const height = 240;
  const left = 64;
  const bottom = 28;
  const top = 12;
  const right = 16;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const groupW = plotW / answer.categories.length;
  const barW = Math.min(36, (groupW * 0.7) / answer.series.length);
  const gap = 2;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={answer.title}>
      {ticks.map((tick) => {
        const y = top + plotH - (tick / max) * plotH;

        return (
          <g key={tick}>
            <line x1={left} x2={width - right} y1={y} y2={y} stroke={GRID} strokeWidth={1} />
            <text x={left - 8} y={y} textAnchor="end" dominantBaseline="middle" fontSize={10} fill={MUTED}>
              {format(tick, answer.unit)}
            </text>
          </g>
        );
      })}

      {answer.categories.map((category, group) => {
        const span = answer.series.length * (barW + gap) - gap;
        const start = left + group * groupW + (groupW - span) / 2;

        return (
          <g key={category}>
            {answer.series.map((series, index) => {
              const value = series.values[group];
              const h = ((value ?? 0) / max) * plotH;
              const x = start + index * (barW + gap);
              const y = top + plotH - h;

              return (
                <g
                  key={series.name}
                  onMouseEnter={(event) => {
                    const box = (event.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                    onTip({
                      x: ((x + barW / 2) / width) * box.width,
                      y: (Math.min(y, top + plotH - 4) / height) * box.height,
                      label: `${series.name} · ${category}`,
                      value: format(value, answer.unit),
                    });
                  }}
                  onMouseLeave={() => onTip(null)}
                >
                  <rect x={x - 2} y={top} width={barW + 4} height={plotH} fill="transparent" />
                  {value !== null && value > 0 && (
                    <path d={bar(x, y, barW, h, false)} fill={SERIES[index % SERIES.length]} />
                  )}
                </g>
              );
            })}
            <text x={left + group * groupW + groupW / 2} y={height - 8} textAnchor="middle" fontSize={11} fill={INK}>
              {category}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function Table({ answer }: { answer: ChartAnswer }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[0.8125rem]">
        <thead>
          <tr className="border-b border-[var(--color-rule)]">
            {answer.columns.map((column, index) => (
              <th key={`${column}-${index}`} className="label py-1.5 pr-4 font-normal">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {answer.rows.map((row, index) => (
            <tr key={index} className="border-b border-[var(--color-rule)] last:border-0">
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className={`tabular py-1.5 pr-4 ${cellIndex === 0 ? "text-[var(--color-ink-soft)]" : "text-[var(--color-ink)]"}`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
