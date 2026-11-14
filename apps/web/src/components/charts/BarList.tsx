export type Bar = { key: string; label: string; value: number; text: string; hint?: string };

/**
 * One measure over named rows: horizontal bars in the first series colour, the value at the end
 * of each bar, the exact figure also in the row's title. Single series, so no legend; the heading
 * names it. Rows with 0 keep their label and figure but draw no bar (no stub).
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
              className="grid grid-cols-[minmax(0,1fr)_8rem] items-center gap-x-3 gap-y-1 text-sm md:grid-cols-[minmax(6rem,10rem)_minmax(0,1fr)_8rem]"
              title={`${r.label}: ${r.text}${r.hint ? `, ${r.hint}` : ""}`}
            >
              <span className="col-span-2 min-w-0 truncate text-default-600 md:col-span-1">{r.label}</span>
              {/* the track takes what the figure leaves, the bar is a share of the track: 3 vs 2 looks 3:2 */}
              <span className="min-w-0">
                {r.value > 0 && (
                  <span
                    className="block h-4 min-w-0.5 rounded-r"
                    style={{ width: `${(r.value / max) * 100}%`, background: "var(--series-1)" }}
                  />
                )}
              </span>
              <span className="min-w-0 shrink-0 text-right tabular-nums leading-tight">
                <span className="block truncate whitespace-nowrap">{r.text}</span>
                {r.hint && <span className="block truncate whitespace-nowrap text-xs text-default-500">{r.hint.replace(/^·\s*/, "")}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
