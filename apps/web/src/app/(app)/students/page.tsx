"use client";

import { useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import clsx from "clsx";


import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { Pager } from "@/components/Pager";
import { EmptyState, QueryState } from "@/components/QueryState";
import { SelectField } from "@/components/SelectField";
import { ListSkeleton, PillsSkeleton } from "@/components/Skeletons";
import { ReviewChip } from "@/components/ReviewChip";
import { PersonStatus } from "@/components/StatusChip";
import { useCanChange, useEducationSummary } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { dushanbeDay, telHref } from "@/lib/format";
import { notifyError } from "@/lib/toast";
import { fullDate, STUDENT_STATUSES } from "@/lib/education";
import type { Paged, StudentRow } from "@/lib/types";

const StudentFormModal = dynamic(() => import("./StudentFormModal").then((m) => m.StudentFormModal));

const PAGE_SIZE = 25;

function Phone({ value }: { value: string | null }) {
  return value ? (
    <a className="inline-flex items-center gap-1.5 text-brand-text" href={telHref(value)}>
      <Icon name="phone" size={14} />
      {value}
    </a>
  ) : (
    <span className="text-default-500">—</span>
  );
}

export default function StudentsPage() {
  const canChange = useCanChange("students");
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const summary = useEducationSummary();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [branch, setBranch] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [review, setReview] = useState(false);
  const queryClient = useQueryClient();
  const clear = useMutation({
    mutationFn: (s: StudentRow) =>
      api(`/api/v1/students/${s.id}`, { method: "PATCH", body: { needs_review: false }, version: s.version }),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["students"] }),
    onError: notifyError,
  });

  const list = useQuery({
    queryKey: ["students", q, status, branch, review, page],
    queryFn: () =>
      api<Paged<StudentRow>>("/api/v1/students", {
        params: {
          q: q.trim() || undefined,
          status: status ?? undefined,
          branch_id: branch ?? undefined,
          needs_review: review ? "true" : undefined,
          page: String(page),
          page_size: String(PAGE_SIZE),
        },
      }),
    placeholderData: keepPreviousData,
  });

  const pick = (next: string | null) => {
    setStatus(next);
    setPage(1);
  };
  const students = list.data?.items ?? [];
  const counts = summary.data?.students;

  return (
    <>
      <PageHeader
        actions={
          <>
            <ExportButton params={{ q: q.trim(), status, branch_id: branch, needs_review: review ? "true" : null }} path="/api/v1/students/export" />
            {canChange && (
              <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setCreating(true)}>
                Студент
              </Button>
            )}
          </>
        }
        title="Студенты"
      />

      {!counts && <PillsSkeleton count={5} />}
      {counts && (
        <div className="mb-4 flex gap-2 overflow-x-auto pb-1 text-sm" role="group" aria-label="Статус студента">
          {[null, ...STUDENT_STATUSES].map((s) => (
            <button
              key={s ?? "all"}
              aria-pressed={status === s}
              className={clsx(
                "shrink-0 rounded-full px-3 py-1 transition-colors",
                status === s ? "bg-primary text-primary-foreground" : "bg-content1 hover:bg-default-100",
              )}
              type="button"
              onClick={() => pick(s)}
            >
              {s ?? "Все"}: <b>{counts[s ?? "всего"]}</b>
            </button>
          ))}
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          className="flex-1 md:max-w-xs md:flex-none"
          isClearable
          placeholder="Поиск: имя или телефон"
          startContent={<Icon name="search" size={18} />}
          value={q}
          onClear={() => {
            setQ("");
            setPage(1);
          }}
          onValueChange={(v) => {
            setQ(v);
            setPage(1);
          }}
        />
        <button
          aria-pressed={review}
          className={clsx(
            "shrink-0 rounded-full px-3 py-1.5 text-sm transition-colors",
            review ? "bg-warning text-warning-foreground" : "bg-content1 hover:bg-default-100",
          )}
          type="button"
          onClick={() => {
            setReview(!review);
            setPage(1);
          }}
        >
          Нужна проверка
        </button>
        {!me?.branch && (
          <SelectField
            allLabel="Все филиалы"
            className="w-full md:w-48"
            label="Филиал"
            options={branches.map((b) => ({ key: b.id, label: b.name }))}
            value={branch}
            onChange={(b) => {
              setBranch(b);
              setPage(1);
            }}
          />
        )}
      </div>

      <QueryState
        empty={
          <EmptyState
            action={
              canChange && !q.trim() && !status && !branch && !review ? (
                <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setCreating(true)}>
                  Студент
                </Button>
              ) : undefined
            }
            hint={q.trim() || status || branch || review ? "Измените поиск или фильтры." : undefined}
            title={q.trim() || status || branch || review ? "Студентов не найдено" : "Нет студентов"}
          />
        }
        isEmpty={(d) => d.items.length === 0}
        query={list}
        skeleton={<ListSkeleton cols={6} />}
      >
        <>
          <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-divider text-xs text-default-500">
                <tr>
                  <th className="px-4 py-3 font-medium">ФИО</th>
                  <th className="px-4 py-3 font-medium">Телефон</th>
                  <th className="px-4 py-3 font-medium">Филиал</th>
                  <th className="px-4 py-3 font-medium">Статус</th>
                  <th className="px-4 py-3 font-medium">Зачислений</th>
                  <th className="px-4 py-3 font-medium">Добавлен</th>
                </tr>
              </thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.id} className="border-b border-divider last:border-0 hover:bg-default-50">
                    <td className="px-4 py-3 font-medium">
                      <Link className="hover:text-brand-text" href={`/students/${s.id}`}>
                        {s.full_name}
                      </Link>
                      {s.needs_review && (
                        <div className="mt-1">
                          <ReviewChip
                            clearing={clear.isPending && clear.variables?.id === s.id}
                            reason={s.review_reason}
                            onClear={canChange ? () => clear.mutate(s) : undefined}
                          />
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Phone value={s.phone} />
                    </td>
                    <td className="px-4 py-3">{s.branch_name}</td>
                    <td className="px-4 py-3">
                      <PersonStatus status={s.status} />
                    </td>
                    <td className="px-4 py-3">{s.enrollments_count}</td>
                    <td className="px-4 py-3 text-default-600">{fullDate(dushanbeDay(s.created_at))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul data-rows className="space-y-3 md:hidden">
            {students.map((s) => (
              <li key={s.id} className="rounded-2xl bg-content1 p-4">
                <div className="flex items-start justify-between gap-2">
                  <Link className="min-w-0 truncate font-medium" href={`/students/${s.id}`}>
                    {s.full_name}
                  </Link>
                  <PersonStatus status={s.status} />
                </div>
                <div className="mt-1 text-sm text-default-500">
                  {s.branch_name} · зачислений: {s.enrollments_count}
                </div>
                <div className="mt-2 text-sm">
                  <Phone value={s.phone} />
                </div>
                {s.needs_review && (
                  <div className="mt-2">
                    <ReviewChip
                      clearing={clear.isPending && clear.variables?.id === s.id}
                      reason={s.review_reason}
                      onClear={canChange ? () => clear.mutate(s) : undefined}
                    />
                  </div>
                )}
              </li>
            ))}
          </ul>
          <Pager page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} onChange={setPage} />
        </>
      </QueryState>

      {creating && <StudentFormModal student={null} onClose={() => setCreating(false)} />}
    </>
  );
}
