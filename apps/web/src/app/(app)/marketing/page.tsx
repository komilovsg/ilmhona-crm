"use client";

import { useState } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { Input } from "@heroui/input";

import { CampaignFormModal } from "./CampaignFormModal";
import { LeadsChart } from "./LeadsChart";

import { ConfirmModal } from "@/components/ConfirmModal";
import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, QueryState } from "@/components/QueryState";
import { RowMenu } from "@/components/RowMenu";
import { SelectField } from "@/components/SelectField";
import { Bone, ListSkeleton } from "@/components/Skeletons";
import { StatCards, StatCardsSkeleton } from "@/components/StatCards";
import { useBranches, useMe } from "@/hooks/queries";
import { useCanChangeSales, useRefreshSales } from "@/hooks/sales";
import { api } from "@/lib/api";
import { formatPrice, fullDate } from "@/lib/education";
import { CAMPAIGN_STATUSES, campaignTone, moneyOrDash, PLATFORMS } from "@/lib/sales";
import type { CampaignList, CampaignRow } from "@/lib/sales-types";
import { notify, notifyError } from "@/lib/toast";

type Filters = { q: string; status: string | null; platform: string | null; branch: string | null; from: string; to: string };
const NO_FILTERS: Filters = { q: "", status: null, platform: null, branch: null, from: "", to: "" };

function paramsOf(f: Filters) {
  return {
    q: f.q.trim() || undefined,
    status: f.status ?? undefined,
    platform: f.platform ?? undefined,
    branch_id: f.branch ?? undefined,
    date_from: f.from || undefined,
    date_to: f.to || undefined,
  };
}

function Period({ c }: { c: CampaignRow }) {
  return (
    <>
      {fullDate(c.start_date)}
      {c.end_date ? ` – ${fullDate(c.end_date)}` : ""}
    </>
  );
}

export default function MarketingPage() {
  const canChange = useCanChangeSales("marketing");
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const refresh = useRefreshSales();
  const [f, setF] = useState<Filters>(NO_FILTERS);
  const [editing, setEditing] = useState<CampaignRow | "new" | null>(null);
  const [removing, setRemoving] = useState<CampaignRow | null>(null);
  const filtered = JSON.stringify(f) !== JSON.stringify(NO_FILTERS);

  const list = useQuery({
    queryKey: ["campaigns", f],
    queryFn: () => api<CampaignList>("/api/v1/campaigns", { params: paramsOf(f) }),
    placeholderData: keepPreviousData,
  });
  const remove = useMutation({
    mutationFn: (c: CampaignRow) => api(`/api/v1/campaigns/${c.id}`, { method: "DELETE" }),
    onSuccess: () => {
      void refresh();
      setRemoving(null);
      notify("Кампания удалена");
    },
    onError: (e) => {
      setRemoving(null);
      notifyError(e);
    },
  });
  const t = list.data?.totals;
  const actions = [
    { key: "edit", label: "Изменить", icon: "edit" },
    { key: "delete", label: "Удалить", icon: "trash", danger: true },
  ];
  const onAction = (c: CampaignRow, key: string) => (key === "edit" ? setEditing(c) : setRemoving(c));
  const add = (
    <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setEditing("new")}>
      Кампания
    </Button>
  );

  return (
    <>
      <PageHeader
        actions={
          <>
            <ExportButton params={paramsOf(f)} path="/api/v1/campaigns/export" />
            {canChange && add}
          </>
        }
        title="Маркетинг"
      />

      {!t && <StatCardsSkeleton count={4} />}
      {t && (
        <StatCards
          stats={[
            { label: "Бюджет", value: formatPrice(t.budget), hint: `Кампаний: ${t.campaigns}` },
            { label: "Лиды", value: String(t.leads), hint: `CPL: ${moneyOrDash(t.cpl)}` },
            { label: "Записались", value: String(t.converted), hint: `CAC: ${moneyOrDash(t.cac)}` },
            { label: "Зачислено в потоки", value: String(t.enrolled) },
          ]}
        />
      )}

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Input
          isClearable
          placeholder="Поиск по названию"
          startContent={<Icon name="search" size={18} />}
          value={f.q}
          onClear={() => setF({ ...f, q: "" })}
          onValueChange={(q) => setF({ ...f, q })}
        />
        <SelectField allLabel="Любой статус" label="Статус" options={CAMPAIGN_STATUSES.map((s) => ({ key: s, label: s }))} value={f.status} onChange={(status) => setF({ ...f, status })} />
        <SelectField allLabel="Все платформы" label="Платформа" options={PLATFORMS.map((s) => ({ key: s, label: s }))} value={f.platform} onChange={(platform) => setF({ ...f, platform })} />
        {!me?.branch && (
          <SelectField allLabel="Все филиалы" label="Филиал" options={branches.map((b) => ({ key: b.id, label: b.name }))} value={f.branch} onChange={(branch) => setF({ ...f, branch })} />
        )}
        <Input label="Старт с" type="date" value={f.from} onValueChange={(from) => setF({ ...f, from })} />
        <Input label="Старт по" type="date" value={f.to} onValueChange={(to) => setF({ ...f, to })} />
      </div>

      <QueryState
        empty={
          <EmptyState
            action={canChange && !filtered ? add : undefined}
            hint={filtered ? "Измените поиск или фильтры." : undefined}
            title={filtered ? "Кампаний не найдено" : "Нет кампаний"}
          />
        }
        isEmpty={(d) => d.items.length === 0}
        query={list}
        skeleton={
          <>
            <Bone className="mb-5 h-56 w-full rounded-2xl" />
            <ListSkeleton cols={9} />
          </>
        }
      >
        {(data) => (
          <>
            <LeadsChart items={data.items} />
            <div className="hidden overflow-x-auto rounded-2xl bg-content1 md:block">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-divider text-xs text-default-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Кампания</th>
                    <th className="px-4 py-3 font-medium">Курс · филиал</th>
                    <th className="px-4 py-3 font-medium">Платформа</th>
                    <th className="px-4 py-3 font-medium">Период</th>
                    <th className="px-4 py-3 text-right font-medium">Бюджет</th>
                    <th className="px-4 py-3 text-right font-medium">Лиды</th>
                    <th className="px-4 py-3 text-right font-medium">Зачислено</th>
                    <th className="px-4 py-3 text-right font-medium">CPL</th>
                    <th className="px-4 py-3 text-right font-medium">CAC</th>
                    <th className="px-4 py-3 font-medium">Статус</th>
                    <th className="w-12 px-2 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((c) => (
                    <tr key={c.id} className="border-b border-divider last:border-0 hover:bg-default-50">
                      <td className="px-4 py-3 font-medium">{c.name}</td>
                      <td className="px-4 py-3">
                        <div>{c.course_name ?? "—"}</div>
                        <div className="text-xs text-default-500">{c.branch_name}</div>
                      </td>
                      <td className="px-4 py-3">{c.platform}</td>
                      <td className="px-4 py-3 text-default-600">
                        <Period c={c} />
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums whitespace-nowrap">{formatPrice(c.budget)}</td>
                      <td className="px-4 py-3 text-right tabular-nums whitespace-nowrap">{c.leads}</td>
                      <td className="px-4 py-3 text-right tabular-nums whitespace-nowrap">{c.enrolled}</td>
                      <td className="px-4 py-3 text-right tabular-nums whitespace-nowrap">{moneyOrDash(c.cpl)}</td>
                      <td className="px-4 py-3 text-right tabular-nums whitespace-nowrap">{moneyOrDash(c.cac)}</td>
                      <td className="px-4 py-3">
                        <Chip color={campaignTone(c.status)} size="sm" variant="flat">
                          {c.status}
                        </Chip>
                      </td>
                      <td className="px-2 py-3">
                        {canChange && <RowMenu actions={actions} label={`Действия: ${c.name}`} onAction={(k) => onAction(c, k)} />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="space-y-3 md:hidden">
              {data.items.map((c) => (
                <li key={c.id} className="rounded-2xl bg-content1 p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate font-medium">{c.name}</div>
                      <div className="text-sm text-default-500">
                        {[c.platform, c.course_name, c.branch_name].filter(Boolean).join(" · ")}
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <Chip color={campaignTone(c.status)} size="sm" variant="flat">
                        {c.status}
                      </Chip>
                      {canChange && <RowMenu actions={actions} label={`Действия: ${c.name}`} onAction={(k) => onAction(c, k)} />}
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-default-500">
                    <Period c={c} />
                  </div>
                  <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
                    {[
                      ["Бюджет", formatPrice(c.budget)],
                      ["Лиды", String(c.leads)],
                      ["Зачислено", String(c.enrolled)],
                      ["CPL", moneyOrDash(c.cpl)],
                      ["CAC", moneyOrDash(c.cac)],
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
          </>
        )}
      </QueryState>

      {editing && <CampaignFormModal campaign={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {removing && (
        <ConfirmModal
          confirmLabel="Удалить"
          danger
          isLoading={remove.isPending}
          isOpen
          title="Удалить кампанию"
          onClose={() => setRemoving(null)}
          onConfirm={() => remove.mutate(removing)}
        >
          Кампания «{removing.name}» будет удалена. Если у неё есть лиды, удалить не получится.
        </ConfirmModal>
      )}
    </>
  );
}
