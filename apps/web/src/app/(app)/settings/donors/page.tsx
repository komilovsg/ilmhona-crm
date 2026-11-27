"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";

import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, QueryState } from "@/components/QueryState";
import { RowMenu } from "@/components/RowMenu";
import { Segmented } from "@/components/Segmented";
import { SelectField } from "@/components/SelectField";
import { ListSkeleton } from "@/components/Skeletons";
import { useCanChange } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { useUrlState } from "@/hooks/url-state";
import { api } from "@/lib/api";
import { fullDate } from "@/lib/education";
import { lazyModal } from "@/lib/lazy-modal";
import { notify, notifyError } from "@/lib/toast";

import type { Donor } from "./DonorFormModal";

const DonorFormModal = lazyModal(() => import("./DonorFormModal").then((m) => m.DonorFormModal));

type View = "list" | "report";
type ReportRow = {
  donor_id: string;
  donor_name: string;
  cohort_id: string;
  cohort_code: string;
  course_name: string;
  branch_name: string;
  start_date: string;
  end_date: string;
  enrolled: number;
  studying: number;
  completed: number;
  expelled: number;
  graduated: number;
  employed: number;
};
type Report = { items: ReportRow[] };

const COUNTS: { key: keyof ReportRow; label: string }[] = [
  { key: "enrolled", label: "Зачислено" },
  { key: "studying", label: "Учится" },
  { key: "expelled", label: "Отчислено" },
  { key: "graduated", label: "Выпустилось" },
  { key: "employed", label: "Трудоустроено" },
];

const NO_FILTERS: { view: string; donor: string | null; branch: string | null } = { view: "list", donor: null, branch: null };

export default function DonorsPage() {
  const [f, setF] = useUrlState(NO_FILTERS);
  const view = (f.view === "report" ? "report" : "list") as View;

  return (
    <>
      <p className="mb-1 text-sm text-default-500">Настройки</p>
      <PageHeader title="Доноры" />
      <div className="mb-4">
        <Segmented
          label="Раздел"
          options={[
            { key: "list", label: "Список" },
            { key: "report", label: "Отчёт" },
          ]}
          value={view}
          onChange={(v) => setF({ view: v })}
        />
      </div>
      {view === "list" ? <DonorList /> : <DonorReport branch={f.branch} donor={f.donor} set={setF} />}
    </>
  );
}

function DonorList() {
  const canChange = useCanChange("donors");
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Donor | "new" | null>(null);
  const list = useQuery({ queryKey: ["donors", "list"], queryFn: () => api<Donor[]>("/api/v1/donors") });
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["donors"] });
  const archive = useMutation({
    mutationFn: (d: Donor) => api(`/api/v1/donors/${d.id}`, { method: "PATCH", body: { archived: !d.archived }, version: d.version }),
    onSuccess: (_, d) => {
      refresh();
      notify(d.archived ? "Донор возвращён" : "Донор в архиве");
    },
    onError: (e) => {
      refresh();
      notifyError(e);
    },
  });
  const menu = (d: Donor) =>
    canChange && (
      <RowMenu
        actions={[
          { key: "edit", label: "Изменить", icon: "edit" },
          { key: "archive", label: d.archived ? "Вернуть из архива" : "В архив", icon: "archive" },
        ]}
        label={`Действия: ${d.name}`}
        onAction={(k) => (k === "edit" ? setForm(d) : archive.mutate(d))}
      />
    );
  const usage = (d: Donor) => `Потоков: ${d.cohorts} · студентов: ${d.students}`;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-end gap-2">
        <ExportButton path="/api/v1/donors/export" />
        {canChange && (
          <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setForm("new")}>
            Донор
          </Button>
        )}
      </div>
      <QueryState
        empty={<EmptyState hint={canChange ? "Добавьте первого кнопкой «Донор»." : undefined} title="Доноров пока нет" />}
        isEmpty={(d) => d.length === 0}
        query={list}
        skeleton={<ListSkeleton cols={4} rows={5} />}
      >
        {(donors) => (
          <ul data-rows className="divide-y divide-divider rounded-2xl bg-content1">
            {donors.map((d) => (
              <li key={d.id} className="flex items-start justify-between gap-2 p-4">
                <div className="min-w-0">
                  <div className="break-words font-medium">
                    {d.name}
                    {d.archived && <span className="font-normal text-default-500"> · в архиве</span>}
                  </div>
                  {d.note && <div className="break-words text-sm text-default-500">{d.note}</div>}
                  <div className="mt-1 text-sm text-default-600">{usage(d)}</div>
                </div>
                {menu(d)}
              </li>
            ))}
          </ul>
        )}
      </QueryState>
      {form && <DonorFormModal donor={form === "new" ? null : form} onClose={() => setForm(null)} onSaved={refresh} />}
    </>
  );
}

function DonorReport({
  donor,
  branch,
  set,
}: {
  donor: string | null;
  branch: string | null;
  set: (f: Partial<typeof NO_FILTERS>) => void;
}) {
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const donors = useQuery({ queryKey: ["donors", "list"], queryFn: () => api<Donor[]>("/api/v1/donors") });
  const params = { donor_id: donor ?? undefined, branch_id: branch ?? undefined };
  const report = useQuery({
    queryKey: ["donors", "report", donor, branch],
    queryFn: () => api<Report>("/api/v1/donors/report", { params }),
  });

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <SelectField filter
          allLabel="Все доноры"
          className="w-full md:w-56"
          label="Донор"
          options={(donors.data ?? []).map((d) => ({ key: d.id, label: d.name }))}
          value={donor}
          onChange={(v) => set({ donor: v })}
        />
        {!me?.branch && (
          <SelectField filter
            allLabel="Все филиалы"
            className="w-full md:w-48"
            label="Филиал"
            options={branches.map((b) => ({ key: b.id, label: b.name }))}
            value={branch}
            onChange={(v) => set({ branch: v })}
          />
        )}
        <div className="ml-auto">
          <ExportButton params={{ donor_id: donor, branch_id: branch }} path="/api/v1/donors/report/export" />
        </div>
      </div>
      <QueryState
        empty={<EmptyState title="У доноров пока нет студентов" />}
        isEmpty={(d) => d.items.length === 0}
        query={report}
        skeleton={<ListSkeleton cols={6} rows={5} />}
      >
        {(data) => (
          <>
            <div className="hidden overflow-x-auto rounded-2xl bg-content1 md:block">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-divider text-xs text-default-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Донор</th>
                    <th className="px-4 py-3 font-medium">Поток</th>
                    {COUNTS.map((c) => (
                      <th key={c.key} className="px-3 py-3 text-right font-medium">
                        {c.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r) => (
                    <tr key={`${r.donor_id}-${r.cohort_id}`} className="border-b border-divider last:border-0 hover:bg-default-50">
                      <td className="px-4 py-3 font-medium">{r.donor_name}</td>
                      <td className="px-4 py-3">
                        <Link className="text-brand-text" href={`/cohorts/${r.cohort_id}`}>
                          {r.cohort_code}
                        </Link>{" "}
                        <span className="text-default-500">{r.course_name}</span>
                      </td>
                      {COUNTS.map((c) => (
                        <td key={c.key} className="px-3 py-3 text-right tabular-nums">
                          {r[c.key]}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul data-rows className="space-y-3 md:hidden">
              {data.items.map((r) => (
                <li key={`${r.donor_id}-${r.cohort_id}`} className="rounded-2xl bg-content1 p-4">
                  <div className="break-words font-medium">{r.donor_name}</div>
                  <div className="break-words text-sm">
                    <Link className="text-brand-text" href={`/cohorts/${r.cohort_id}`}>
                      {r.cohort_code}
                    </Link>{" "}
                    {r.course_name}
                  </div>
                  <div className="text-xs text-default-500">
                    {fullDate(r.start_date)} – {fullDate(r.end_date)}
                  </div>
                  <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                    {COUNTS.map((c) => (
                      <div key={c.key} className="flex justify-between gap-2">
                        <dt className="text-default-500">{c.label}</dt>
                        <dd className="tabular-nums">{r[c.key]}</dd>
                      </div>
                    ))}
                  </dl>
                </li>
              ))}
            </ul>
          </>
        )}
      </QueryState>
    </>
  );
}
