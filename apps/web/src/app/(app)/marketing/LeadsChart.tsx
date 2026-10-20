import type { CampaignRow } from "@/lib/sales-types";

const MAX_BARS = 12;

/**
 * Leads per campaign: one measure, one series, so one colour (the brand blue, which reads on
 * both surfaces) and no legend. Horizontal bars with a 4px rounded data end on the baseline,
 * the number at the end of each bar; the exact table is the campaign list right below.
 */
export function LeadsChart({ items }: { items: CampaignRow[] }) {
  const rows = [...items].sort((a, b) => b.leads - a.leads || a.name.localeCompare(b.name, "ru")).slice(0, MAX_BARS);
  const max = Math.max(1, ...rows.map((r) => r.leads));
  const summary = rows.map((r) => `${r.name}: ${r.leads}`).join("; ");

  return (
    <section aria-labelledby="leads-chart" className="mb-5 rounded-2xl bg-content1 p-4">
      <h2 className="mb-3 text-sm font-medium" id="leads-chart">
        Лиды по кампаниям
        {items.length > MAX_BARS && <span className="font-normal text-default-500"> · {MAX_BARS} крупнейших</span>}
      </h2>
      <ul aria-label={summary} className="space-y-2" role="img">
        {rows.map((r) => (
          <li
            key={r.id}
            className="grid grid-cols-[minmax(5rem,9rem)_1fr] items-center gap-3 text-sm md:grid-cols-[12rem_1fr]"
            title={`${r.name}: лидов ${r.leads}, записалось ${r.converted}`}
          >
            <span className="truncate text-default-600">{r.name}</span>
            <span className="flex items-center gap-2">
              <span
                className="h-4 min-w-0.5 rounded-r bg-brand-text"
                style={{ width: `${(r.leads / max) * 100}%`, maxWidth: "calc(100% - 2.5rem)" }}
              />
              <span className="w-8 shrink-0 tabular-nums">{r.leads}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
