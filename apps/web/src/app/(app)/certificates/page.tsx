"use client";

import { useState } from "react";
import Link from "next/link";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";

import { CertCommentModal } from "@/components/certs/CertCommentModal";
import { DateField } from "@/components/DateField";
import { ExportButton } from "@/components/ExportButton";
import { useUrlPage, useUrlState } from "@/hooks/url-state";
import { FilterInput } from "@/components/FilterInput";
import { PageHeader } from "@/components/PageHeader";
import { NoPrefix, NoTd, NoTh, rowNo } from "@/components/RowNo";
import { Pager } from "@/components/Pager";
import { EmptyState, QueryState } from "@/components/QueryState";
import { RowMenu, type MenuAction } from "@/components/RowMenu";
import { SelectField } from "@/components/SelectField";
import { ListSkeleton } from "@/components/Skeletons";
import { fetchCertPdf, saveBytes, toastNotReady, useCanIssueCerts, useRefreshIssued, useTemplates } from "@/hooks/certs";
import { useCourses, useInstructors } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { STATUS_LABEL, STATUS_TONE, type CertRow, type CertStatus } from "@/lib/certs";
import { formatDate } from "@/lib/format";
import { can } from "@/lib/permissions";
import type { Paged } from "@/lib/reports-types";
import { notify, notifyError } from "@/lib/toast";

const PAGE_SIZE = 25;
type Filters = {
  q: string;
  status: CertStatus | null;
  branch: string | null;
  course: string | null;
  instructor: string | null;
  template: string | null;
  batch: string | null;
  from: string;
  to: string;
};
const NO_FILTERS: Filters = { q: "", status: null, branch: null, course: null, instructor: null, template: null, batch: null, from: "", to: "" };
const STATUS_OPTIONS = (Object.keys(STATUS_LABEL) as CertStatus[]).map((key) => ({ key, label: STATUS_LABEL[key] }));

function paramsOf(f: Filters) {
  return {
    q: f.q.trim() || undefined,
    status: f.status ?? undefined,
    branch_id: f.branch ?? undefined,
    course_id: f.course ?? undefined,
    instructor_id: f.instructor ?? undefined,
    template_id: f.template ?? undefined,
    batch_id: f.batch ?? undefined,
    date_from: f.from || undefined,
    date_to: f.to || undefined,
  };
}

function StatusBadge({ status }: { status: CertStatus }) {
  return (
    <Chip color={STATUS_TONE[status]} size="sm" variant="flat">
      {STATUS_LABEL[status]}
    </Chip>
  );
}

/** The holder: a link to the student card when the certificate is linked to one, plain text otherwise. */
function Who({ r, block }: { r: CertRow; block?: boolean }) {
  if (!r.student_id) return <span className={block ? "block min-w-0 truncate font-medium" : undefined}>{r.student_name}</span>;

  return (
    <Link className={block ? "block min-w-0 truncate font-medium" : "hover:text-brand-text"} href={`/students/${r.student_id}`}>
      {r.student_name}
    </Link>
  );
}

type Pending = { row: CertRow; kind: "reissue" | "revoke" };

export default function CertificatesPage() {
  const { data: me } = useMe();
  const canChange = useCanIssueCerts();
  const { data: branches = [] } = useBranches();
  const { data: courses = [] } = useCourses();
  const { data: instructors = [] } = useInstructors();
  const seesTemplates = !!me && can(me.permissions, "cert_templates", "view");
  const templates = useTemplates(seesTemplates);
  const refresh = useRefreshIssued();
  const [f, setF] = useUrlState(NO_FILTERS);
  const [page, setPage] = useUrlPage();
  const [pending, setPending] = useState<Pending | null>(null);
  const filtered = JSON.stringify(f) !== JSON.stringify(NO_FILTERS);
  const set = (next: Filters) => {
    setF(next);
    setPage(1);
  };

  const list = useQuery({
    queryKey: ["certificates", f, page],
    queryFn: () => api<Paged<CertRow>>("/api/v1/certificates", { params: { ...paramsOf(f), page: String(page), page_size: String(PAGE_SIZE) } }),
    placeholderData: keepPreviousData,
  });

  const download = useMutation({
    mutationFn: async (r: CertRow) => {
      const { data, name } = await fetchCertPdf(r.id);

      saveBytes(data, name ?? `${r.number}.pdf`, "application/pdf");
    },
    onError: notifyError,
  });
  const act = useMutation({
    mutationFn: ({ row, kind, text }: Pending & { text: string }) =>
      kind === "reissue"
        ? api(`/api/v1/certificates/${row.id}/reissue`, { method: "POST", body: { comment: text } })
        : api(`/api/v1/certificates/${row.id}/revoke`, { method: "POST", body: { reason: text } }),
    onSuccess: (_, { kind }) => {
      void refresh();
      setPending(null);
      notify(kind === "reissue" ? "Сертификат перевыпущен" : "Сертификат аннулирован");
    },
    onError: (e) => {
      void refresh();
      setPending(null);
      if (!toastNotReady(e)) notifyError(e);
    },
  });

  const actions = (r: CertRow): MenuAction[] => [
    { key: "pdf", label: "Скачать", icon: "download" },
    ...(canChange && r.status === "valid"
      ? [
          ...(r.cohort_id ? [{ key: "reissue", label: "Перевыпустить", icon: "edit" }] : []),
          { key: "revoke", label: "Аннулировать", icon: "ban", danger: true },
        ]
      : []),
  ];
  const onAction = (r: CertRow, key: string) => (key === "pdf" ? download.mutate(r) : setPending({ row: r, kind: key as Pending["kind"] }));
  const menu = (r: CertRow) => <RowMenu actions={actions(r)} label={`Действия: ${r.number}`} onAction={(k) => onAction(r, k)} />;

  return (
    <>
      <PageHeader
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {canChange && (
              <Button as={Link} color="primary" href="/certificates/bulk" variant="flat">
                Выдать из Excel
              </Button>
            )}
            {seesTemplates && (
              <Button as={Link} href="/settings/certificates" variant="flat">
                Настройки
              </Button>
            )}
            <ExportButton label="Выгрузить в Excel" params={{ ...paramsOf(f), format: "xlsx" }} path="/api/v1/certificates" />
          </div>
        }
        title="Сертификаты"
      />
      {f.batch && (
        <div className="mb-3">
          <Chip variant="flat" onClose={() => set({ ...f, batch: null })}>
            Только партия из Excel
          </Chip>
        </div>
      )}
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <FilterInput isClearable placeholder="Поиск по номеру или ФИО" value={f.q} onClear={() => set({ ...f, q: "" })} onValueChange={(q) => set({ ...f, q })} />
        <SelectField filter allLabel="Любой статус" label="Статус" options={STATUS_OPTIONS} value={f.status} onChange={(status) => set({ ...f, status: status as CertStatus | null })} />
        {!me?.branch && (
          <SelectField filter allLabel="Все филиалы" label="Филиал" options={branches.map((b) => ({ key: b.id, label: b.name }))} value={f.branch} onChange={(branch) => set({ ...f, branch })} />
        )}
        <SelectField filter allLabel="Все курсы" label="Курс" options={courses.map((c) => ({ key: c.id, label: c.name }))} value={f.course} onChange={(course) => set({ ...f, course })} />
        <SelectField filter allLabel="Все инструкторы" label="Инструктор" options={instructors.map((i) => ({ key: i.id, label: i.full_name }))} value={f.instructor} onChange={(instructor) => set({ ...f, instructor })} />
        {seesTemplates && (
          <SelectField filter allLabel="Все шаблоны" label="Шаблон" options={(templates.data?.items ?? []).map((t) => ({ key: t.id, label: t.name }))} value={f.template} onChange={(template) => set({ ...f, template })} />
        )}
        <DateField filter label="Выдан с" max={f.to || undefined} value={f.from} onValueChange={(from) => set({ ...f, from })} />
        <DateField filter label="Выдан по" min={f.from || undefined} value={f.to} onValueChange={(to) => set({ ...f, to })} />
      </div>

      <QueryState
        empty={<EmptyState hint={filtered ? "Измените поиск или фильтры." : "Сертификаты появятся здесь после выдачи в карточке потока."} title={filtered ? "Сертификаты не найдены" : "Сертификатов пока нет"} />}
        isEmpty={(d) => d.items.length === 0}
        query={list}
        skeleton={<ListSkeleton cols={8} />}
      >
        {(d) => (
          <>
            <div className="hidden overflow-x-auto rounded-2xl bg-content1 md:block">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-divider text-xs text-default-500">
                  <tr>
                    <NoTh />
                    <th className="px-4 py-3 font-medium">Номер</th>
                    <th className="px-4 py-3 font-medium">ФИО</th>
                    <th className="px-4 py-3 font-medium">Курс · поток</th>
                    <th className="px-4 py-3 font-medium">Инструктор</th>
                    <th className="px-4 py-3 font-medium">Дата · выдал</th>
                    <th className="px-4 py-3 font-medium">Шаблон</th>
                    <th className="px-4 py-3 font-medium">Статус</th>
                    <th className="w-12 px-2 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {d.items.map((r, i) => (
                    <tr key={r.id} className="border-b border-divider last:border-0 hover:bg-default-50">
                      <NoTd n={rowNo(page, PAGE_SIZE, i)} />
                      <td className="px-4 py-3 font-medium whitespace-nowrap">{r.number}</td>
                      <td className="px-4 py-3">
                        <Who r={r} />
                      </td>
                      <td className="px-4 py-3">
                        <div>{r.course_name ?? "—"}</div>
                        {r.cohort_id && (
                          <Link className="text-xs text-brand-text" href={`/cohorts/${r.cohort_id}`}>
                            {r.cohort_code}
                          </Link>
                        )}
                        <span className="text-xs text-default-500">
                          {r.cohort_id ? " · " : "Список Excel · "}
                          {r.branch_name}
                        </span>
                      </td>
                      <td className="px-4 py-3">{r.instructor_name ?? "—"}</td>
                      <td className="px-4 py-3">
                        <div className="whitespace-nowrap">{formatDate(r.issued_at)}</div>
                        <div className="text-xs text-default-500">{r.issued_by_name ?? "—"}</div>
                      </td>
                      <td className="px-4 py-3">{r.template_name}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={r.status} />
                        {r.revoke_reason && <div className="mt-1 max-w-48 text-xs text-default-500">{r.revoke_reason}</div>}
                      </td>
                      <td className="px-2 py-3">{menu(r)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul data-rows className="space-y-3 md:hidden">
              {d.items.map((r, i) => (
                <li key={r.id} className="rounded-2xl bg-content1 p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-sm font-medium">{r.number}</div>
                      <div className="flex min-w-0 items-baseline">
                        <NoPrefix n={rowNo(page, PAGE_SIZE, i)} />
                        <Who block r={r} />
                      </div>
                      <div className="text-sm text-default-500">{[r.course_name, r.cohort_code].filter(Boolean).join(" · ") || "Список Excel"}</div>
                    </div>
                    <div className="flex items-center gap-1">
                      <StatusBadge status={r.status} />
                      {menu(r)}
                    </div>
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    {[
                      ["Дата", formatDate(r.issued_at)],
                      ["Филиал", r.branch_name],
                      ["Инструктор", r.instructor_name ?? "—"],
                      ["Шаблон", r.template_name],
                      ["Выдал", r.issued_by_name ?? "—"],
                      ...(r.revoke_reason ? [["Причина", r.revoke_reason]] : []),
                    ].map(([k, v]) => (
                      <div key={k}>
                        <dt className="text-xs text-default-500">{k}</dt>
                        <dd className="font-medium">{v}</dd>
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

      {pending && (
        <CertCommentModal
          confirmLabel={pending.kind === "reissue" ? "Перевыпустить" : "Аннулировать"}
          danger={pending.kind === "revoke"}
          intro={
            pending.kind === "reissue"
              ? `Сертификат ${pending.row.number} (${pending.row.student_name}) станет «Заменён», выдастся новый с тем же номером и актуальными данными.`
              : `Сертификат ${pending.row.number} (${pending.row.student_name}) станет «Аннулирован». Отменить это нельзя.`
          }
          isLoading={act.isPending}
          label={pending.kind === "reissue" ? "Комментарий" : "Причина аннулирования"}
          title={pending.kind === "reissue" ? "Перевыпустить сертификат" : "Аннулировать сертификат"}
          onClose={() => setPending(null)}
          onSubmit={(text) => act.mutate({ ...pending, text })}
        />
      )}
    </>
  );
}
