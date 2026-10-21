"use client";

import { useEffect, useRef, useState } from "react";

import { compact, niceTicks } from "@/lib/reports";

export type TrendSeries = { key: string; label: string; color: string; values: number[] };

const HEIGHT = 240;
const PAD = { top: 12, right: 16, bottom: 26, left: 52 };

/** The width of an element, followed on resize: the SVG is drawn at its real pixel size, so
 * the text stays 11-12px on a phone instead of scaling down with a viewBox. */
function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = ref.current;

    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));

    observer.observe(el);

    return () => observer.disconnect();
  }, []);

  return [ref, width] as const;
}

/**
 * Lines over time, one shared y axis (never two), 2px strokes, a legend that is always there,
 * a crosshair with a tooltip on hover or touch, a zero line for negatives and a table view for
 * everybody who prefers numbers (also the screen-reader path).
 */
export function TrendChart({
  title,
  labels,
  fullLabels,
  series,
  format,
}: {
  title: string;
  labels: string[];
  fullLabels: string[];
  series: TrendSeries[];
  format: (n: number) => string;
}) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const all = series.flatMap((s) => s.values);
  const ticks = niceTicks(Math.min(0, ...all), Math.max(0, ...all));
  const lo = ticks[0];
  const hi = ticks[ticks.length - 1];
  const innerW = Math.max(0, width - PAD.left - PAD.right);
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (labels.length > 1 ? (i / (labels.length - 1)) * innerW : innerW / 2);
  const y = (v: number) => PAD.top + innerH - ((v - lo) / (hi - lo || 1)) * innerH;
  const every = width < 480 ? 2 : 1;

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - box.left - PAD.left) / (innerW || 1)) * (labels.length - 1));

    setHover(Math.min(labels.length - 1, Math.max(0, i)));
  };

  return (
    <section aria-label={title} className="rounded-2xl bg-content1 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium">{title}</h2>
        <button className="text-xs text-brand-text underline" type="button" onClick={() => setTable(!table)}>
          {table ? "График" : "Таблица"}
        </button>
      </div>
      <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-default-600">
        {series.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span aria-hidden="true" className="h-0.5 w-4 rounded" style={{ background: s.color }} />
            {s.label}
          </li>
        ))}
      </ul>
      {table ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-divider text-xs text-default-500">
              <tr>
                <th className="py-2 pr-3 font-medium">Месяц</th>
                {series.map((s) => (
                  <th key={s.key} className="px-2 py-2 text-right font-medium">
                    {s.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fullLabels.map((l, i) => (
                <tr key={l} className="border-b border-divider last:border-0">
                  <td className="py-2 pr-3">{l}</td>
                  {series.map((s) => (
                    <td key={s.key} className="px-2 py-2 text-right tabular-nums whitespace-nowrap">
                      {format(s.values[i])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={ref} className="relative" style={{ height: HEIGHT }}>
          {width > 0 && (
            <svg
              aria-label={`${title}: ${series.map((s) => s.label).join(", ")} по месяцам`}
              height={HEIGHT}
              role="img"
              style={{ touchAction: "pan-y" }}
              width={width}
              onPointerLeave={() => setHover(null)}
              onPointerMove={onMove}
            >
              {ticks.map((t) => (
                <g key={t}>
                  <line
                    stroke={t === 0 ? "currentColor" : "var(--chart-grid)"}
                    strokeOpacity={t === 0 ? 0.35 : 1}
                    x1={PAD.left}
                    x2={width - PAD.right}
                    y1={y(t)}
                    y2={y(t)}
                  />
                  <text className="fill-default-500" fontSize="11" textAnchor="end" x={PAD.left - 8} y={y(t) + 4}>
                    {compact(t)}
                  </text>
                </g>
              ))}
              {labels.map((l, i) =>
                i % every === (labels.length - 1) % every ? (
                  <text key={`${l}${i}`} className="fill-default-500" fontSize="11" textAnchor="middle" x={x(i)} y={HEIGHT - 8}>
                    {l}
                  </text>
                ) : null,
              )}
              {hover !== null && <line stroke="var(--chart-grid)" strokeWidth="1.5" x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + innerH} />}
              {series.map((s) => (
                <g key={s.key}>
                  <polyline
                    fill="none"
                    points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")}
                    stroke={s.color}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                  />
                  {hover !== null && (
                    <circle cx={x(hover)} cy={y(s.values[hover])} fill={s.color} r="4.5" stroke="var(--heroui-content1, white)" strokeWidth="2" />
                  )}
                </g>
              ))}
            </svg>
          )}
          {hover !== null && width > 0 && (
            <div
              className="pointer-events-none absolute top-2 z-10 rounded-lg bg-content2 px-3 py-2 text-xs shadow-md"
              style={{ left: x(hover) > width / 2 ? undefined : x(hover) + 12, right: x(hover) > width / 2 ? width - x(hover) + 12 : undefined }}
            >
              <div className="mb-1 font-medium">{fullLabels[hover]}</div>
              {series.map((s) => (
                <div key={s.key} className="flex items-center justify-between gap-4">
                  <span className="flex items-center gap-1.5 text-default-600">
                    <span aria-hidden="true" className="size-2 rounded-full" style={{ background: s.color }} />
                    {s.label}
                  </span>
                  <span className="tabular-nums">{format(s.values[hover])}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
