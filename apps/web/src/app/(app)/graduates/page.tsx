"use client";

import { useState } from "react";
import Link from "next/link";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Chip } from "@heroui/chip";
import { Input } from "@heroui/input";

import { EmploymentFormModal } from "./EmploymentFormModal";

import { ConfirmModal } from "@/components/ConfirmModal";
import { ExportButton } from "@/components/ExportButton";
import { PageHeader } from "@/components/PageHeader";
import { Pager } from "@/components/Pager";
import { EmptyState, QueryState } from "@/components/QueryState";
import { RowMenu } from "@/components/RowMenu";
import { Segmented } from "@/components/Segmented";
import { SelectField } from "@/components/SelectField";
import { ListSkeleton } from "@/components/Skeletons";
import { useCourses } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { useCanChangeGraduates, useRefreshReports } from "@/hooks/reports";
import { api } from "@/lib/api";
import { formatPrice, fullDate } from "@/lib/education";
import { dushanbeDay } from "@/lib/format";
import { orDash } from "@/lib/reports";
import { percentLabel } from "@/lib/sales";
import type { GraduateCourseRow, GraduateRow, Paged } from "@/lib/reports-types";
import { notify, notifyError } from "@/lib/toast";

const PAGE_SIZE = 25;
type View = "students" | "courses";
type Filters = { q: string; branch: string | null; course: string | null; employed: string | null; certificate: string | null };
const NO_FILTERS: Filters = { q: "", branch: null, course: null, employed: null, certificate: null };
const YES_NO = [
  { key: "true", label: "Да" },
  { key: "false", label: "Нет" },
];

function paramsOf(f: Filters) {
  return {
    q: f.q.trim() || undefined,
    branch_id: f.branch ?? undefined,
    course_id: f.course ?? undefined,
    employed: f.employed ?? undefined,
    certificate: f.certificate ?? undefined,
  };
}

export default function GraduatesPage() {
  const canChange = useCanChangeGraduates();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const { data: courses = [] } = useCourses();
  const refresh = useRefreshReports();
  const [view, setView] = useState<View>("students");
  const [f, setF] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [job, setJob] = useState<GraduateRow | null>(null);
  const [issuing, setIssuing] = useState<GraduateRow | null>(null);
  const filtered = JSON.stringify(f) !== JSON.stringify(NO_FILTERS);
  const set = (next: Filters) => {
    setF(next);
    setPage(1);
  };

  const list = useQuery({
    queryKey: ["graduates", f, page],
    queryFn: () => api<Paged<GraduateRow>>("/api/v1/graduates/students", { params: { ...paramsOf(f), page: String(page), page_size: String(PAGE_SIZE) } }),
    placeholderData: keepPreviousData,
    enabled: view === "students",
  });
  const byCourse = useQuery({
    queryKey: ["graduate-courses", f.branch],
    queryFn: () => api<{ items: GraduateCourseRow[] }>("/api/v1/graduates/courses", { params: { branch_id: f.branch ?? undefined } }),
    placeholderData: keepPreviousData,
    enabled: view === "courses",
  });
  const issue = useMutation({
    mutationFn: (g: GraduateRow) => api<{ certificate_no: string }>(`/api/v1/graduates/${g.enrollment_id}/certificate`, { method: "POST" }),
    onSuccess: (r) => {
      void refresh();
      setIssuing(null);
      notify(`Сертификат ${r.certificate_no} выдан`);
    },
    onError: (e) => {
      setIssuing(null);
      notifyError(e);
    },
  });
  const actions = (g: GraduateRow) => [
    ...(g.certificate_no ? [] : [{ key: "cert", label: "Выдать сертификат", icon: "graduates" }]),
    { key: "job", label: "Добавить трудоустройство", icon: "plus" },
  ];
  const onAction = (g: GraduateRow, key: string) => (key === "cert" ? setIssuing(g) : setJob(g));

  return (
    <>
      <PageHeader
        actions={
          <>
            <Link className="text-sm text-brand-text" href="/employment">
              Трудоустройство
            </Link>
            <ExportButton params={view === "students" ? paramsOf(f) : { branch_id: f.branch }} path={`/api/v1/graduates/${view}/export`} />
          </>
        }
        title="Выпускники"
      />
      <Segmented
        className="mb-4"
        label="Вид"
        options={[
          { key: "students", label: "По студентам" },
          { key: "courses", label: "По курсам" },
        ]}
        value={view}
        onChange={setView}
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {view === "students" && (
          <Input isClearable placeholder="Поиск по имени или телефону" value={f.q} onClear={() => set({ ...f, q: "" })} onValueChange={(q) => set({ ...f, q })} />
        )}
        {!me?.branch && (
          <SelectField allLabel="Все филиалы" label="Филиал" options={branches.map((b) => ({ key: b.id, label: b.name }))} value={f.branch} onChange={(branch) => set({ ...f, branch })} />
        )}
        {view === "students" && (
          <>
            <SelectField allLabel="Все курсы" label="Курс" options={courses.map((c) => ({ key: c.id, label: c.name }))} value={f.course} onChange={(course) => set({ ...f, course })} />
            <SelectField allLabel="Любой" label="Трудоустроен" options={YES_NO} value={f.employed} onChange={(employed) => set({ ...f, employed })} />
            <SelectField allLabel="Любой" label="Сертификат" options={YES_NO} value={f.certificate} onChange={(certificate) => set({ ...f, certificate })} />
          </>
        )}
      </div>

      {view === "students" && (
        <QueryState
          empty={<EmptyState hint={filtered ? "Измените поиск или фильтры." : "Выпускниками становятся студенты с баллом 70+ после окончания потока."} title={filtered ? "Выпускников не найдено" : "Выпускников пока нет"} />}
          isEmpty={(d) => d.items.length === 0}
          query={list}
          skeleton={<ListSkeleton cols={9} />}
        >
          {(d) => (
            <>
              <div className="hidden overflow-x-auto rounded-2xl bg-content1 md:block">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-divider text-xs text-default-500">
                    <tr>
                      <th className="px-4 py-3 font-medium">Студент</th>
                      <th className="px-4 py-3 font-medium">Курс · инструктор</th>
                      <th className="px-4 py-3 font-medium">Зачислен</th>
                      <th className="px-4 py-3 text-right font-medium">Балл</th>
                      <th className="px-4 py-3 text-right font-medium">Оплачено</th>
                      <th className="px-4 py-3 font-medium">Сертификат</th>
                      <th className="px-4 py-3 font-medium">Трудоустроен</th>
                      <th className="w-12 px-2 py-3" />
                    </tr>
                  </thead>
                  <tbody>
                    {d.items.map((g) => (
                      <tr key={g.enrollment_id} className="border-b border-divider last:border-0 hover:bg-default-50">
                        <td className="px-4 py-3">
                          <Link className="font-medium hover:text-brand-text" href={`/students/${g.student_id}`}>
                            {g.student_name}
                          </Link>
                          <div className="text-xs text-default-500">{g.branch_name}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div>{g.course_name}</div>
                          <div className="text-xs text-default-500">{[g.cohort_code, g.instructor_name].filter(Boolean).join(" · ")}</div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">{fullDate(dushanbeDay(g.enrolled_at))}</td>
                        <td className="px-4 py-3 text-right tabular-nums">{g.score}</td>
                        <td className="px-4 py-3 text-right tabular-nums whitespace-nowrap">{orDash(g.paid, formatPrice)}</td>
                        <td className="px-4 py-3 whitespace-nowrap">{g.certificate_no ?? "—"}</td>
                        <td className="px-4 py-3">{g.employed ? g.organization : "—"}</td>
                        <td className="px-2 py-3">{canChange && <RowMenu actions={actions(g)} label={`Действия: ${g.student_name}`} onAction={(k) => onAction(g, k)} />}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ul className="space-y-3 md:hidden">
                {d.items.map((g) => (
                  <li key={g.enrollment_id} className="rounded-2xl bg-content1 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <Link className="block truncate font-medium" href={`/students/${g.student_id}`}>
                          {g.student_name}
                        </Link>
                        <div className="text-sm text-default-500">{[g.course_name, g.cohort_code].join(" · ")}</div>
                        {g.instructor_name && <div className="text-xs text-default-500">{g.instructor_name}</div>}
                      </div>
                      <div className="flex items-center gap-1">
                        <Chip color="success" size="sm" variant="flat">
                          {g.score} б.
                        </Chip>
                        {canChange && <RowMenu actions={actions(g)} label={`Действия: ${g.student_name}`} onAction={(k) => onAction(g, k)} />}
                      </div>
                    </div>
                    <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                      {[
                        ["Зачислен", fullDate(dushanbeDay(g.enrolled_at))],
                        ["Оплачено", orDash(g.paid, formatPrice)],
                        ["Сертификат", g.certificate_no ?? "—"],
                        ["Трудоустроен", g.employed ? (g.organization ?? "Да") : "—"],
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
      )}

      {view === "courses" && (
        <QueryState
          empty={<EmptyState title="Выпускников пока нет" />}
          isEmpty={(d) => d.items.length === 0}
          query={byCourse}
          skeleton={<ListSkeleton cols={4} />}
        >
          {(d) => (
            <div className="overflow-x-auto rounded-2xl bg-content1">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-divider text-xs text-default-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Курс</th>
                    <th className="px-4 py-3 text-right font-medium">Выпускников</th>
                    <th className="px-4 py-3 text-right font-medium">Средний балл</th>
                    <th className="px-4 py-3 text-right font-medium">Трудоустроено</th>
                  </tr>
                </thead>
                <tbody>
                  {d.items.map((c) => (
                    <tr key={c.course_id} className="border-b border-divider last:border-0">
                      <td className="px-4 py-3 font-medium">{c.course_name}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{c.graduates}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{c.avg_score}</td>
                      <td className="px-4 py-3 text-right tabular-nums whitespace-nowrap">
                        {c.employed} · {percentLabel(c.employed_percent)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryState>
      )}

      {job && <EmploymentFormModal enrollmentId={job.enrollment_id} job={null} student={{ id: job.student_id, name: job.student_name }} onClose={() => setJob(null)} />}
      {issuing && (
        <ConfirmModal
          confirmLabel="Выдать"
          isLoading={issue.isPending}
          isOpen
          title="Выдать сертификат"
          onClose={() => setIssuing(null)}
          onConfirm={() => issue.mutate(issuing)}
        >
          Студенту {issuing.student_name} будет выдан сертификат с новым номером. Отменить это нельзя: статус «выпускник» больше не изменится.
        </ConfirmModal>
      )}
    </>
  );
}
