"use client";

import { useState } from "react";

import { useWidth } from "./TrendChart";

import { pct, weekRange, type WeekPoint } from "@/lib/analytics";

const HEIGHT = 200;
const PAD = { top: 10, right: 12, bottom: 26, left: 40 };
const TICKS = [0, 25, 50, 75, 100];

/**
 * Attendance by ISO week: thin bars on one 0–100 % axis, a dashed target line that is labelled
 * (never colour alone), a tooltip on hover or touch, a table view for numbers and screen readers.
 * A week without marks keeps its slot (no bar, «—»): a gap is data, a missing week is not.
 */
export function WeekBars({ weeks, target }: { weeks: WeekPoint[]; target: number }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const innerW = Math.max(0, width - PAD.left - PAD.right);
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const slot = innerW / Math.max(1, weeks.length);
  const barW = Math.min(18, Math.max(6, slot * 0.4));
  const cx = (i: number) => PAD.left + slot * i + slot / 2;
  const y = (v: number) => PAD.top + innerH - (v / 100) * innerH;
  // label every n-th week so the dates never collide
  const every = Math.max(1, Math.ceil(weeks.length / Math.max(1, Math.floor(innerW / 64))));
  const summary = weeks.map((w) => `${weekRange(w)}: ${pct(w.percent)}`).join("; ");
  const point = hover === null ? null : weeks[hover];

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-default-600">
          <li className="flex items-center gap-1.5">
            <span aria-hidden="true" className="h-3 w-1.5 rounded-sm" style={{ background: "var(--series-1)" }} />
            посещаемость недели
          </li>
          <li className="flex items-center gap-1.5">
            <span aria-hidden="true" className="w-4 border-t-2 border-dashed border-default-500" />
            цель {target} %
          </li>
        </ul>
        <button className="text-xs text-brand-text underline" type="button" onClick={() => setTable(!table)}>
          {table ? "График" : "Таблица"}
        </button>
      </div>
      {table ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-divider text-xs text-default-500">
              <tr>
                <th className="py-2 pr-3 font-medium">Неделя</th>
                <th className="px-2 py-2 text-right font-medium">Уроков</th>
                <th className="px-2 py-2 text-right font-medium">Отметок</th>
                <th className="px-2 py-2 text-right font-medium">Пришли</th>
                <th className="px-2 py-2 text-right font-medium">Посещаемость</th>
              </tr>
            </thead>
            <tbody>
              {weeks.map((w) => (
                <tr key={w.week_start} className="border-b border-divider last:border-0">
                  <td className="py-2 pr-3 whitespace-nowrap">{weekRange(w)}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{w.lessons}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{w.marked}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{w.present}</td>
                  <td className="px-2 py-2 text-right tabular-nums whitespace-nowrap">{pct(w.percent)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={ref} className="relative" style={{ height: HEIGHT }}>
          {width > 0 && (
            <svg
              aria-label={`Посещаемость по неделям, цель ${target} %. ${summary}`}
              height={HEIGHT}
              role="img"
              style={{ touchAction: "pan-y" }}
              width={width}
              onPointerLeave={() => setHover(null)}
              onPointerMove={(e) => {
                const box = e.currentTarget.getBoundingClientRect();
                const i = Math.floor((e.clientX - box.left - PAD.left) / (slot || 1));

                setHover(i >= 0 && i < weeks.length ? i : null);
              }}
            >
              {TICKS.map((t) => (
                <g key={t}>
                  <line stroke="var(--chart-grid)" x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} />
                  <text className="fill-default-500" fontSize="11" textAnchor="end" x={PAD.left - 6} y={y(t) + 4}>
                    {t}
                  </text>
                </g>
              ))}
              {weeks.map((w, i) => (
                <g key={w.week_start}>
                  {w.percent !== null && (
                    <rect
                      fill="var(--series-1)"
                      height={Math.max(1, (w.percent / 100) * innerH)}
                      opacity={hover === null || hover === i ? 1 : 0.55}
                      rx="2"
                      width={barW}
                      x={cx(i) - barW / 2}
                      y={y(w.percent)}
                    />
                  )}
                  {i % every === 0 && (
                    <text className="fill-default-500" fontSize="11" textAnchor="middle" x={cx(i)} y={HEIGHT - 8}>
                      {weeks.length === 1 ? weekRange(w) : w.week_start.slice(8) + "." + w.week_start.slice(5, 7)}
                    </text>
                  )}
                </g>
              ))}
              <line stroke="currentColor" strokeDasharray="5 4" strokeOpacity="0.55" strokeWidth="1.5" x1={PAD.left} x2={width - PAD.right} y1={y(target)} y2={y(target)} />
            </svg>
          )}
          {point && hover !== null && width > 0 && (
            <div
              className="pointer-events-none absolute top-1 z-10 rounded-lg bg-content2 px-3 py-2 text-xs shadow-md"
              style={{ left: cx(hover) > width / 2 ? undefined : cx(hover) + 12, right: cx(hover) > width / 2 ? width - cx(hover) + 12 : undefined }}
            >
              <div className="mb-1 font-medium">{weekRange(point)}</div>
              <div className="tabular-nums">{pct(point.percent)}</div>
              <div className="text-default-500">
                {point.present} из {point.marked} отметок · уроков {point.lessons}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
