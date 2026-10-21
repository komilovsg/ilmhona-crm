"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { Input } from "@heroui/input";
import clsx from "clsx";


import { ConfirmModal } from "@/components/ConfirmModal";
import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { InlineSelect } from "@/components/InlineSelect";
import { PageHeader } from "@/components/PageHeader";
import { Pager } from "@/components/Pager";
import { EmptyState, QueryState } from "@/components/QueryState";
import { RowMenu } from "@/components/RowMenu";
import { Segmented } from "@/components/Segmented";
import { SelectField } from "@/components/SelectField";
import { ListSkeleton, PillsSkeleton } from "@/components/Skeletons";
import { useCourses } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { useCanChange } from "@/hooks/education";
import { useCanChangeSales, useRefreshSales } from "@/hooks/sales";
import { api } from "@/lib/api";
import { fullDate } from "@/lib/education";
import { dushanbeDay, formatDateTime, telHref } from "@/lib/format";
import {
  CALL_STATUSES,
  callTone,
  LEAD_SOURCES,
  LEAD_STATUSES,
  leadTone,
  percentLabel,
  telegramHref,
  whatsappHref,
} from "@/lib/sales";
import type { Duplicates, LeadFunnel, LeadRow } from "@/lib/sales-types";
import { notify, notifyError } from "@/lib/toast";
import type { Paged } from "@/lib/types";

const ConvertModal = dynamic(() => import("./ConvertModal").then((m) => m.ConvertModal));
const DuplicatesNotice = dynamic(() => import("./DuplicatesNotice").then((m) => m.DuplicatesNotice));
const ImportWizard = dynamic(() => import("./ImportWizard").then((m) => m.ImportWizard));
const LeadFormModal = dynamic(() => import("./LeadFormModal").then((m) => m.LeadFormModal));

const PAGE_SIZE = 25;
const OPEN_STATUSES = LEAD_STATUSES.filter((s) => s !== "записан");

type Filters = {
  q: string;
  status: string | null;
  call: string | null;
  source: string | null;
  course: string | null;
  branch: string | null;
  from: string;
  to: string;
  review: boolean;
};
const NO_FILTERS: Filters = { q: "", status: null, call: null, source: null, course: null, branch: null, from: "", to: "", review: false };

/** The query of the list, the funnel and the export: one place, so they always agree. */
function paramsOf(f: Filters, withStatus: boolean) {
  return {
    q: f.q.trim() || undefined,
    status: withStatus ? (f.status ?? undefined) : undefined,
    call_status: f.call ?? undefined,
    source: f.source ?? undefined,
    course_id: f.course ?? undefined,
    branch_id: f.branch ?? undefined,
    date_from: f.from || undefined,
    date_to: f.to || undefined,
    needs_review: f.review ? "true" : undefined,
  };
}

/** Big «Позвонить» + WhatsApp + Telegram: the thing a manager does with a lead. */
function PhoneActions({ lead, big }: { lead: LeadRow; big?: boolean }) {
  if (!lead.phone) return <span className="text-default-500">нет телефона</span>;
  const wa = whatsappHref(lead.phone);
  const tg = telegramHref(lead.phone);
  const size = big ? "h-12 text-base" : "h-8 text-xs";

  return (
    <div className={clsx("flex items-center gap-2", big && "w-full flex-wrap")}>
      <a
        className={clsx(
          "inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-4 font-medium text-primary-foreground",
          size,
          big && "basis-full",
        )}
        href={telHref(lead.phone)}
      >
        <Icon name="phone" size={big ? 20 : 14} />
        {big ? "Позвонить" : lead.phone}
      </a>
      {wa && (
        <a
          aria-label="WhatsApp"
          className={clsx("inline-flex items-center justify-center gap-1.5 rounded-xl bg-success/15 px-3 font-medium text-success-700 dark:text-success", size, big && "min-w-0 flex-1")}
          href={wa}
          rel="noreferrer"
          target="_blank"
        >
          <Icon name="message" size={big ? 20 : 14} />
          {big && "WhatsApp"}
        </a>
      )}
      {tg && (
        <a
          aria-label="Telegram"
          className={clsx("inline-flex items-center justify-center gap-1.5 rounded-xl bg-primary/10 px-3 font-medium text-brand-text", size, big && "min-w-0 flex-1")}
          href={tg}
          rel="noreferrer"
          target="_blank"
        >
          <Icon name="send" size={big ? 20 : 14} />
          {big && "Telegram"}
        </a>
      )}
    </div>
  );
}

function NameCell({ lead }: { lead: LeadRow }) {
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{lead.full_name}</span>
        {lead.needs_review && (
          <Chip color="warning" size="sm" title={lead.raw_name ? `Пришло из формы: ${lead.raw_name}` : undefined} variant="flat">
            проверить
          </Chip>
        )}
      </div>
      {lead.comment && <div className="mt-0.5 line-clamp-1 text-xs text-default-500">{lead.comment}</div>}
    </div>
  );
}

export default function LeadsPage() {
  const canChange = useCanChangeSales("leads");
  const canConvert = useCanChange("students"); // convert creates or links a student
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const { data: courses = [] } = useCourses();
  const refresh = useRefreshSales();
  const [tab, setTab] = useState<"all" | "callback">("all");
  const [f, setF] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<LeadRow | "new" | null>(null);
  const [converting, setConverting] = useState<LeadRow | null>(null);
  const [removing, setRemoving] = useState<LeadRow | null>(null);
  const [importing, setImporting] = useState(false);
  const [warn, setWarn] = useState<{ name: string; duplicates: Duplicates } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const callback = tab === "callback";

  const set = (next: Partial<Filters>) => {
    setF((cur) => ({ ...cur, ...next }));
    setPage(1);
  };
  const filtered = JSON.stringify(f) !== JSON.stringify(NO_FILTERS);

  const list = useQuery({
    queryKey: ["leads", f, tab, page],
    queryFn: () =>
      api<Paged<LeadRow>>("/api/v1/leads", {
        params: { ...paramsOf(f, true), callback: callback ? "true" : undefined, page: String(page), page_size: String(PAGE_SIZE) },
      }),
    placeholderData: keepPreviousData,
  });
  const funnel = useQuery({
    queryKey: ["lead-funnel", { ...f, status: null }],
    queryFn: () => api<LeadFunnel>("/api/v1/metrics/leads", { params: paramsOf(f, false) }),
    placeholderData: keepPreviousData,
  });

  const change = useMutation({
    mutationFn: (v: { lead: LeadRow; body: Record<string, unknown>; key: string }) =>
      api<LeadRow>(`/api/v1/leads/${v.lead.id}`, { method: "PATCH", body: v.body, version: v.lead.version }),
    onMutate: (v) => setBusy(v.key),
    onSuccess: () => void refresh(),
    onError: (e) => {
      notifyError(e);
      void refresh();
    },
    onSettled: () => setBusy(null),
  });
  const remove = useMutation({
    mutationFn: (lead: LeadRow) => api(`/api/v1/leads/${lead.id}`, { method: "DELETE" }),
    onSuccess: () => {
      void refresh();
      setRemoving(null);
      notify("Лид удалён");
    },
    onError: notifyError,
  });

  const leads = list.data?.items ?? [];
  const counts = funnel.data?.counts;
  const rowActions = (l: LeadRow) => [
    ...(canConvert
      ? [{ key: "convert", label: l.status === "записан" ? "Записать в ещё один поток" : "Записать в поток", icon: "user-plus" }]
      : []),
    { key: "edit", label: "Изменить", icon: "edit" },
    { key: "delete", label: "Удалить", icon: "trash", danger: true },
  ];
  const onAction = (l: LeadRow, key: string) => {
    if (key === "convert") setConverting(l);
    else if (key === "edit") setEditing(l);
    else setRemoving(l);
  };
  const statusSelect = (l: LeadRow) => (
    <InlineSelect
      busy={busy === `${l.id}:status`}
      disabled={!canChange || l.status === "записан"}
      label={`Статус: ${l.full_name}`}
      options={l.status === "записан" ? ["записан"] : OPEN_STATUSES}
      tone={leadTone(l.status)}
      value={l.status}
      onChange={(status) => change.mutate({ lead: l, body: { status }, key: `${l.id}:status` })}
    />
  );
  const callSelect = (l: LeadRow) => (
    <InlineSelect
      busy={busy === `${l.id}:call`}
      disabled={!canChange}
      label={`Звонок: ${l.full_name}`}
      options={CALL_STATUSES}
      tone={callTone(l.call_status)}
      value={l.call_status}
      onChange={(call_status) => change.mutate({ lead: l, body: { call_status }, key: `${l.id}:call` })}
    />
  );

  const newLead = (
    <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setEditing("new")}>
      Лид
    </Button>
  );

  return (
    <>
      <PageHeader
        actions={
          <>
            {canChange && (
              <Button isIconOnly aria-label="Импорт CSV" className="md:hidden" variant="flat" onPress={() => setImporting(true)}>
                <Icon name="upload" size={18} />
              </Button>
            )}
            {canChange && (
              <Button className="hidden md:inline-flex" startContent={<Icon name="upload" size={18} />} variant="flat" onPress={() => setImporting(true)}>
                Импорт CSV
              </Button>
            )}
            <ExportButton params={{ ...paramsOf(f, true), callback: callback ? "true" : undefined }} path="/api/v1/leads/export" />
            {canChange && newLead}
          </>
        }
        title="Лиды"
      />

      <Segmented
        className="mb-4"
        label="Раздел лидов"
        options={[
          { key: "all", label: "Все лиды" },
          { key: "callback", label: `Перезвонить сегодня${funnel.data ? ` · ${funnel.data.callbacks_today}` : ""}` },
        ]}
        value={tab}
        onChange={(t) => {
          setTab(t);
          setPage(1);
        }}
      />

      {!counts && <PillsSkeleton count={7} />}
      {counts && (
        <div aria-label="Воронка" className="mb-4 flex gap-2 overflow-x-auto pb-1 text-sm" role="group">
          {[null, ...LEAD_STATUSES].map((s) => (
            <button
              key={s ?? "all"}
              aria-pressed={f.status === s}
              className={clsx(
                "shrink-0 rounded-full px-3 py-1 transition-colors",
                f.status === s ? "bg-primary text-primary-foreground" : "bg-content1 hover:bg-default-100",
              )}
              type="button"
              onClick={() => set({ status: s })}
            >
              {s ?? "Все"}: <b>{counts[s ?? "всего"]}</b>
            </button>
          ))}
          <span className="shrink-0 rounded-full bg-success/15 px-3 py-1 text-success-700 dark:text-success" title="Записано ÷ все лиды">
            Конверсия: <b>{percentLabel(funnel.data?.conversion ?? 0)}</b>
          </span>
        </div>
      )}

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Input
          className="sm:col-span-2"
          isClearable
          placeholder="Поиск: имя или телефон"
          startContent={<Icon name="search" size={18} />}
          value={f.q}
          onClear={() => set({ q: "" })}
          onValueChange={(q) => set({ q })}
        />
        <SelectField allLabel="Любой звонок" label="Статус звонка" options={CALL_STATUSES.map((s) => ({ key: s, label: s }))} value={f.call} onChange={(call) => set({ call })} />
        <SelectField allLabel="Все источники" label="Источник" options={LEAD_SOURCES.map((s) => ({ key: s, label: s }))} value={f.source} onChange={(source) => set({ source })} />
        <SelectField allLabel="Все курсы" label="Курс" options={courses.map((c) => ({ key: c.id, label: c.name }))} value={f.course} onChange={(course) => set({ course })} />
        {!me?.branch && (
          <SelectField allLabel="Все филиалы" label="Филиал" options={branches.map((b) => ({ key: b.id, label: b.name }))} value={f.branch} onChange={(branch) => set({ branch })} />
        )}
        <Input label="С даты" type="date" value={f.from} onValueChange={(from) => set({ from })} />
        <Input label="По дату" type="date" value={f.to} onValueChange={(to) => set({ to })} />
        <button
          aria-pressed={f.review}
          className={clsx(
            "flex h-14 items-center justify-center gap-2 rounded-xl px-3 text-sm transition-colors",
            f.review ? "bg-warning/20 text-warning-700 dark:text-warning" : "bg-content1 hover:bg-default-100",
          )}
          type="button"
          onClick={() => set({ review: !f.review })}
        >
          Нужна проверка: <b>{funnel.data?.needs_review ?? 0}</b>
        </button>
      </div>

      <QueryState
        empty={
          <EmptyState
            action={canChange && !filtered && !callback ? newLead : undefined}
            hint={callback ? "На сегодня звонков нет." : filtered ? "Измените поиск или фильтры." : undefined}
            title={callback ? "Некому перезванивать" : filtered ? "Лидов не найдено" : "Нет лидов"}
          />
        }
        isEmpty={(d) => d.items.length === 0}
        query={list}
        skeleton={<ListSkeleton cols={7} />}
      >
        <>
          <div className="hidden overflow-x-auto rounded-2xl bg-content1 md:block">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-divider text-xs text-default-500">
                <tr>
                  <th className="px-4 py-3 font-medium">ФИО</th>
                  <th className="px-4 py-3 font-medium">Телефон</th>
                  <th className="px-4 py-3 font-medium">Курс · источник</th>
                  <th className="px-4 py-3 font-medium">Статус</th>
                  <th className="px-4 py-3 font-medium">Звонок</th>
                  <th className="px-4 py-3 font-medium">Создан</th>
                  <th className="w-12 px-2 py-3" />
                </tr>
              </thead>
              <tbody>
                {leads.map((l) => (
                  <tr key={l.id} className="border-b border-divider align-top last:border-0 hover:bg-default-50">
                    <td className="px-4 py-3">
                      <NameCell lead={l} />
                      <div className="text-xs text-default-500">{l.branch_name}</div>
                    </td>
                    <td className="px-4 py-3">
                      <PhoneActions lead={l} />
                    </td>
                    <td className="px-4 py-3">
                      <div>{l.course_name ?? "—"}</div>
                      <div className="text-xs text-default-500">
                        {l.source}
                        {l.campaign_name ? ` · ${l.campaign_name}` : ""}
                      </div>
                    </td>
                    <td className="px-4 py-3">{statusSelect(l)}</td>
                    <td className="px-4 py-3">
                      <div>{callSelect(l)}</div>
                      {l.next_contact_at && l.call_status === "перезвонить" && (
                        <div className="mt-1 text-xs text-default-500">{formatDateTime(l.next_contact_at)}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-default-600">{fullDate(dushanbeDay(l.created_at))}</td>
                    <td className="px-2 py-3">
                      {canChange && <RowMenu actions={rowActions(l)} label={`Действия: ${l.full_name}`} onAction={(k) => onAction(l, k)} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul data-rows className="space-y-3 md:hidden">
            {leads.map((l) => (
              <li key={l.id} className="space-y-3 rounded-2xl bg-content1 p-4">
                <div className="flex items-start justify-between gap-2">
                  <NameCell lead={l} />
                  {canChange && <RowMenu actions={rowActions(l)} label={`Действия: ${l.full_name}`} onAction={(k) => onAction(l, k)} />}
                </div>
                <div className="text-sm text-default-500">
                  {[l.course_name, l.source, l.branch_name].filter(Boolean).join(" · ")}
                </div>
                <PhoneActions big lead={l} />
                <div className="flex flex-wrap items-center gap-2">
                  {statusSelect(l)}
                  {callSelect(l)}
                </div>
                {l.next_contact_at && l.call_status === "перезвонить" && (
                  <div className="text-xs text-default-500">Перезвонить: {formatDateTime(l.next_contact_at)}</div>
                )}
              </li>
            ))}
          </ul>
          <Pager page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} onChange={setPage} />
        </>
      </QueryState>

      {editing && (
        <LeadFormModal
          lead={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setEditing(null);
            if (saved.duplicates) setWarn({ name: saved.full_name, duplicates: saved.duplicates });
          }}
        />
      )}
      {warn && <DuplicatesNotice duplicates={warn.duplicates} name={warn.name} onClose={() => setWarn(null)} />}
      {converting && <ConvertModal lead={converting} onClose={() => setConverting(null)} />}
      {importing && <ImportWizard onClose={() => setImporting(false)} />}
      {removing && (
        <ConfirmModal
          confirmLabel="Удалить"
          danger
          isLoading={remove.isPending}
          isOpen
          title="Удалить лид"
          onClose={() => setRemoving(null)}
          onConfirm={() => remove.mutate(removing)}
        >
          Лид «{removing.full_name}» будет удалён. Студент, если он уже записан, останется.
        </ConfirmModal>
      )}
    </>
  );
}
