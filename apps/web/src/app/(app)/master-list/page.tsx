"use client";

import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Input } from "@heroui/input";

import { ExportButton } from "@/components/ExportButton";
import { PageHeader } from "@/components/PageHeader";
import { Pager } from "@/components/Pager";
import { EmptyState, QueryState } from "@/components/QueryState";
import { SelectField } from "@/components/SelectField";
import { ListSkeleton } from "@/components/Skeletons";
import { CohortStatus } from "@/components/StatusChip";
import { useBranches, useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { COHORT_STATUSES, formatPrice, fullDate } from "@/lib/education";
import { FORMAT_LABEL, orDash } from "@/lib/reports";
import type { MasterRow, Paged } from "@/lib/reports-types";

const PAGE_SIZE = 25;
const LEADS_NOTE = "Лиды и нулевой урок — лиды этого курса и филиала, созданные за 45 дней до старта потока (включая день старта).";

type Filters = { branch: string | null; status: string | null; from: string; to: string };
const NO_FILTERS: Filters = { branch: null, status: null, from: "", to: "" };

function paramsOf(f: Filters) {
  return { branch_id: f.branch ?? undefined, status: f.status ?? undefined, date_from: f.from || undefined, date_to: f.to || undefined };
}

const NUM = "px-3 py-3 text-right tabular-nums whitespace-nowrap";

export default function MasterListPage() {
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const [f, setF] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const filtered = JSON.stringify(f) !== JSON.stringify(NO_FILTERS);
  const set = (next: Filters) => {
    setF(next);
    setPage(1);
  };

  const list = useQuery({
    queryKey: ["master-list", f, page],
    queryFn: () => api<Paged<MasterRow>>("/api/v1/master-list", { params: { ...paramsOf(f), page: String(page), page_size: String(PAGE_SIZE) } }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader actions={<ExportButton params={paramsOf(f)} path="/api/v1/master-list/export" />} title="Мастер-лист" />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {!me?.branch && (
          <SelectField allLabel="Все филиалы" label="Филиал" options={branches.map((b) => ({ key: b.id, label: b.name }))} value={f.branch} onChange={(branch) => set({ ...f, branch })} />
        )}
        <SelectField allLabel="Любой статус" label="Статус" options={COHORT_STATUSES.map((s) => ({ key: s, label: s }))} value={f.status} onChange={(status) => set({ ...f, status })} />
        <Input label="Старт с" type="date" value={f.from} onValueChange={(from) => set({ ...f, from })} />
        <Input label="Старт по" type="date" value={f.to} onValueChange={(to) => set({ ...f, to })} />
      </div>
      <p className="mb-3 text-xs text-default-500">{LEADS_NOTE}</p>
      <QueryState
        empty={<EmptyState hint={filtered ? "Измените фильтры." : undefined} title={filtered ? "Потоков не найдено" : "Нет потоков"} />}
        isEmpty={(d) => d.items.length === 0}
        query={list}
        skeleton={<ListSkeleton cols={10} />}
      >
        {(d) => (
          <>
            <div className="hidden max-h-[75vh] overflow-auto rounded-2xl bg-content1 md:block">
              <table className="w-max min-w-full border-separate border-spacing-0 text-left text-sm">
                <thead className="text-xs text-default-500">
                  <tr className="[&>th]:sticky [&>th]:top-0 [&>th]:z-10 [&>th]:border-b [&>th]:border-divider [&>th]:bg-content1 [&>th]:px-3 [&>th]:py-3 [&>th]:font-medium">
                    <th className="!left-0 !z-20 w-32 min-w-32">Старт</th>
                    <th className="!left-32 !z-20 min-w-56 border-r !border-r-divider">Курс · поток</th>
                    <th>Конец</th>
                    <th>Формат</th>
                    <th className="text-right">Стоимость/мес</th>
                    <th>Статус</th>
                    <th className="text-right" title={LEADS_NOTE}>Лиды <span className="font-normal">(за 45 дн. до старта)</span></th>
                    <th className="text-right" title={LEADS_NOTE}>Нулевой урок</th>
                    <th className="text-right">Записались</th>
                    <th className="text-right">Оплатили мес. 1</th>
                    <th className="text-right">мес. 2</th>
                    <th className="text-right">мес. 3</th>
                    <th className="text-right">LTV/чел</th>
                    <th className="text-right">Доход</th>
                    <th className="text-right">Выпускников</th>
                    <th className="text-right">Трудоустроено</th>
                  </tr>
                </thead>
                <tbody>
                  {d.items.map((r) => (
                    <tr key={r.cohort_id} className="group [&>td]:border-b [&>td]:border-divider group-last:[&>td]:border-0">
                      <td className="sticky left-0 z-10 w-32 min-w-32 bg-content1 px-3 py-3 whitespace-nowrap group-hover:bg-default-50">{fullDate(r.start_date)}</td>
                      <td className="sticky left-32 z-10 min-w-56 border-r border-divider bg-content1 px-3 py-3 group-hover:bg-default-50">
                        <div className="font-medium">{r.course_name}</div>
                        <div className="text-xs text-default-500">
                          {r.code} · {r.branch_name}
                        </div>
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">{fullDate(r.end_date)}</td>
                      <td className="px-3 py-3">{FORMAT_LABEL[r.format] ?? r.format}</td>
                      <td className={NUM}>{formatPrice(r.price_month)}</td>
                      <td className="px-3 py-3">
                        <CohortStatus status={r.status} />
                      </td>
                      <td className={NUM}>{r.leads}</td>
                      <td className={NUM}>{r.zero_lesson}</td>
                      <td className={NUM}>{r.enrolled}</td>
                      <td className={NUM}>{r.paid_1}</td>
                      <td className={NUM}>{r.paid_2}</td>
                      <td className={NUM}>{r.paid_3}</td>
                      <td className={NUM}>{orDash(r.ltv, formatPrice)}</td>
                      <td className={NUM}>{orDash(r.income, formatPrice)}</td>
                      <td className={NUM}>{r.graduates}</td>
                      <td className={NUM}>{r.employed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul data-rows className="space-y-3 md:hidden">
              {d.items.map((r) => (
                <li key={r.cohort_id} className="rounded-2xl bg-content1 p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate font-medium">{r.course_name}</div>
                      <div className="text-sm text-default-500">
                        {r.code} · {r.branch_name} · {FORMAT_LABEL[r.format] ?? r.format}
                      </div>
                    </div>
                    <CohortStatus status={r.status} />
                  </div>
                  <div className="mt-1 text-xs text-default-500">
                    {fullDate(r.start_date)} – {fullDate(r.end_date)} · {formatPrice(r.price_month)}/мес
                  </div>
                  <dl className="mt-3 grid grid-cols-3 gap-x-2 gap-y-3 text-sm">
                    {[
                      ["Лиды (45 дн.)", String(r.leads)],
                      ["Нулевой урок", String(r.zero_lesson)],
                      ["Записались", String(r.enrolled)],
                      ["Оплатили мес. 1", String(r.paid_1)],
                      ["Мес. 2", String(r.paid_2)],
                      ["Мес. 3", String(r.paid_3)],
                      ["Доход", orDash(r.income, formatPrice)],
                      ["LTV/чел", orDash(r.ltv, formatPrice)],
                      ["Выпускников", String(r.graduates)],
                      ["Трудоустроено", String(r.employed)],
                    ].map(([k, v]) => (
                      <div key={k}>
                        <dt className="text-xs text-default-500">{k}</dt>
                        <dd className="font-medium tabular-nums">{v}</dd>
                      </div>
                    ))}
                  </dl>
                </li>
              ))}
            </ul>
            <Pager page={page} pageSize={PAGE_SIZE} total={d.total} onChange={setPage} />
          </>
        )}
      </QueryState>
    </>
  );
}
