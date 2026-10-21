"use client";

import { useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Input } from "@heroui/input";


import { ConfirmModal } from "@/components/ConfirmModal";
import { ExportButton } from "@/components/ExportButton";
import { PageHeader } from "@/components/PageHeader";
import { Pager } from "@/components/Pager";
import { EmptyState, QueryState } from "@/components/QueryState";
import { RowMenu } from "@/components/RowMenu";
import { SelectField } from "@/components/SelectField";
import { ListSkeleton } from "@/components/Skeletons";
import { useBranches, useMe } from "@/hooks/queries";
import { useCanChangeGraduates, useRefreshReports } from "@/hooks/reports";
import { api } from "@/lib/api";
import { fullDate } from "@/lib/education";
import type { EmploymentRow, Paged } from "@/lib/reports-types";
import { notify, notifyError } from "@/lib/toast";

const EmploymentFormModal = dynamic(() => import("../graduates/EmploymentFormModal").then((m) => m.EmploymentFormModal));

const PAGE_SIZE = 25;
type Filters = { q: string; branch: string | null; from: string; to: string };
const NO_FILTERS: Filters = { q: "", branch: null, from: "", to: "" };

function paramsOf(f: Filters) {
  return { q: f.q.trim() || undefined, branch_id: f.branch ?? undefined, date_from: f.from || undefined, date_to: f.to || undefined };
}

export default function EmploymentPage() {
  const canChange = useCanChangeGraduates();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const refresh = useRefreshReports();
  const [f, setF] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<EmploymentRow | null>(null);
  const [removing, setRemoving] = useState<EmploymentRow | null>(null);
  const filtered = JSON.stringify(f) !== JSON.stringify(NO_FILTERS);
  const set = (next: Filters) => {
    setF(next);
    setPage(1);
  };

  const list = useQuery({
    queryKey: ["employment", f, page],
    queryFn: () => api<Paged<EmploymentRow>>("/api/v1/employment", { params: { ...paramsOf(f), page: String(page), page_size: String(PAGE_SIZE) } }),
    placeholderData: keepPreviousData,
  });
  const remove = useMutation({
    mutationFn: (j: EmploymentRow) => api(`/api/v1/employment/${j.id}`, { method: "DELETE" }),
    onSuccess: () => {
      void refresh();
      setRemoving(null);
      notify("Запись удалена");
    },
    onError: (e) => {
      setRemoving(null);
      notifyError(e);
    },
  });
  const actions = [
    { key: "edit", label: "Изменить", icon: "edit" },
    { key: "delete", label: "Удалить", icon: "trash", danger: true },
  ];
  const onAction = (j: EmploymentRow, key: string) => (key === "edit" ? setEditing(j) : setRemoving(j));

  return (
    <>
      <Link className="mb-3 inline-block text-sm text-default-500 hover:text-foreground" href="/graduates">
        ← Выпускники
      </Link>
      <PageHeader actions={<ExportButton params={paramsOf(f)} path="/api/v1/employment/export" />} title="Трудоустройство" />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Input isClearable placeholder="Студент или организация" value={f.q} onClear={() => set({ ...f, q: "" })} onValueChange={(q) => set({ ...f, q })} />
        {!me?.branch && (
          <SelectField allLabel="Все филиалы" label="Филиал" options={branches.map((b) => ({ key: b.id, label: b.name }))} value={f.branch} onChange={(branch) => set({ ...f, branch })} />
        )}
        <Input label="С" type="date" value={f.from} onValueChange={(from) => set({ ...f, from })} />
        <Input label="По" type="date" value={f.to} onValueChange={(to) => set({ ...f, to })} />
      </div>
      <QueryState
        empty={
          <EmptyState
            hint={filtered ? "Измените поиск или фильтры." : "Место работы добавляется выпускнику: из списка выпускников или со страницы студента."}
            title={filtered ? "Записей не найдено" : "Пока нет трудоустройства"}
          />
        }
        isEmpty={(d) => d.items.length === 0}
        query={list}
        skeleton={<ListSkeleton cols={5} />}
      >
        {(d) => (
          <>
            <div className="hidden overflow-x-auto rounded-2xl bg-content1 md:block">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-divider text-xs text-default-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Студент</th>
                    <th className="px-4 py-3 font-medium">Курс · поток</th>
                    <th className="px-4 py-3 font-medium">Организация</th>
                    <th className="px-4 py-3 font-medium">Должность</th>
                    <th className="px-4 py-3 font-medium">Дата</th>
                    <th className="w-12 px-2 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {d.items.map((j) => (
                    <tr key={j.id} className="border-b border-divider last:border-0 hover:bg-default-50">
                      <td className="px-4 py-3">
                        <Link className="font-medium hover:text-brand-text" href={`/students/${j.student_id}`}>
                          {j.student_name}
                        </Link>
                        <div className="text-xs text-default-500">{j.branch_name}</div>
                      </td>
                      <td className="px-4 py-3">{[j.course_name, j.cohort_code].filter(Boolean).join(" · ") || "—"}</td>
                      <td className="px-4 py-3">{j.organization}</td>
                      <td className="px-4 py-3">{j.position ?? "—"}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{fullDate(j.employed_at)}</td>
                      <td className="px-2 py-3">{canChange && <RowMenu actions={actions} label={`Действия: ${j.student_name}`} onAction={(k) => onAction(j, k)} />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul data-rows className="space-y-3 md:hidden">
              {d.items.map((j) => (
                <li key={j.id} className="rounded-2xl bg-content1 p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <Link className="block truncate font-medium" href={`/students/${j.student_id}`}>
                        {j.student_name}
                      </Link>
                      <div className="text-sm">{j.organization}</div>
                      <div className="text-xs text-default-500">{[j.position, j.course_name, fullDate(j.employed_at)].filter(Boolean).join(" · ")}</div>
                    </div>
                    {canChange && <RowMenu actions={actions} label={`Действия: ${j.student_name}`} onAction={(k) => onAction(j, k)} />}
                  </div>
                </li>
              ))}
            </ul>
            <Pager page={page} pageSize={PAGE_SIZE} total={d.total} onChange={setPage} />
          </>
        )}
      </QueryState>

      {editing && <EmploymentFormModal job={editing} student={{ id: editing.student_id, name: editing.student_name }} onClose={() => setEditing(null)} />}
      {removing && (
        <ConfirmModal
          confirmLabel="Удалить"
          danger
          isLoading={remove.isPending}
          isOpen
          title="Удалить запись"
          onClose={() => setRemoving(null)}
          onConfirm={() => remove.mutate(removing)}
        >
          Запись о работе {removing.student_name} в «{removing.organization}» будет удалена и пропадёт из выпускников и мастер-листа.
        </ConfirmModal>
      )}
    </>
  );
}
