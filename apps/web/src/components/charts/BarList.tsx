export type Bar = { key: string; label: string; value: number; text: string; hint?: string };

/**
 * One measure over named rows: horizontal bars in the first series colour, the value at the end
 * of each bar, the exact figure also in the row's title. Single series, so no legend; the heading
 * names it. Rows with 0 keep their line (an empty bar is data, a missing row is not).
 */
export function BarList({ title, rows, note }: { title: string; rows: Bar[]; note?: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  const summary = rows.map((r) => `${r.label}: ${r.text}`).join("; ");

  return (
    <section aria-label={title} className="rounded-2xl bg-content1 p-4">
      <h2 className="mb-3 text-sm font-medium">
        {title}
        {note && <span className="font-normal text-default-500"> · {note}</span>}
      </h2>
      {rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-default-500">Данных пока нет</p>
      ) : (
        <ul aria-label={summary} className="space-y-2" role="img">
          {rows.map((r) => (
            <li
              key={r.key}
              className="grid grid-cols-[minmax(5rem,8rem)_1fr] items-center gap-3 text-sm md:grid-cols-[10rem_1fr]"
              title={`${r.label}: ${r.text}${r.hint ? `, ${r.hint}` : ""}`}
            >
              <span className="truncate text-default-600">{r.label}</span>
              <span className="flex items-center gap-2">
                <span
                  className="h-4 min-w-0.5 rounded-r"
                  style={{ width: `${(r.value / max) * 100}%`, maxWidth: "calc(100% - 6rem)", background: "var(--series-1)" }}
                />
                <span className="shrink-0 whitespace-nowrap tabular-nums">
                  {r.text}
                  {r.hint && <span className="text-xs text-default-500"> {r.hint}</span>}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
