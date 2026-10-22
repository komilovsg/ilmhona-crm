"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import type { RateRecord } from "./RateModal";

import { ActivateUserButton } from "@/components/ActivateUserButton";
import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, QueryState } from "@/components/QueryState";
import { CardGridSkeleton } from "@/components/Skeletons";
import { CohortStatus } from "@/components/StatusChip";
import { useCanPaySalaries } from "@/hooks/money";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/education";
import { telHref } from "@/lib/format";
import type { InstructorCard, InstructorDetail } from "@/lib/money-types";
import { lazyModal } from "@/lib/lazy-modal";

const RateModal = lazyModal(() => import("./RateModal").then((m) => m.RateModal));

type Editing = { title: string; hint?: string; record: RateRecord; field: string; request: (rate: string, version: number) => Promise<unknown> };

function Number_({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-default-500">{label}</div>
      <div className="truncate text-base font-semibold">{value}</div>
      <div className="h-4 truncate text-xs leading-4 text-default-500">{hint ?? ""}</div>
    </div>
  );
}

function Cohorts({ id, canEdit, edit }: { id: string; canEdit: boolean; edit: (e: Editing) => void }) {
  const detail = useQuery({
    queryKey: ["instructor-detail", id],
    queryFn: () => api<InstructorDetail>(`/api/v1/instructors/${id}`),
  });

  return (
    <QueryState
      empty={<p className="py-3 text-sm text-default-500">У инструктора пока нет потоков.</p>}
      isEmpty={(d) => d.cohorts_list.length === 0}
      query={detail}
      skeleton={<div className="h-24" />}
    >
      {(d) => (
        <ul className="divide-y divide-divider text-sm">
          {d.cohorts_list.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2.5">
              <div className="min-w-0">
                <Link className="font-medium text-brand-text" href={`/cohorts/${c.id}`}>
                  {c.code}
                </Link>{" "}
                <span className="text-default-600">{c.course_name}</span>
                <div className="text-xs text-default-500">
                  студентов: {c.students} · доход {formatPrice(c.income)}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <CohortStatus status={c.status} />
                <span className="whitespace-nowrap font-medium">{formatPrice(c.rate)}/мес</span>
                {canEdit && (
                  <Button
                    isIconOnly
                    aria-label={`Изменить ставку потока ${c.code}`}
                    size="sm"
                    variant="light"
                    onPress={() =>
                      edit({
                        title: `Ставка потока ${c.code}`,
                        hint: "Сколько инструктор получает за каждый месяц этого потока.",
                        record: { version: c.version, instructor_rate: c.rate },
                        field: "instructor_rate",
                        request: (rate, version) =>
                          api(`/api/v1/salaries/cohorts/${c.id}/rate`, { method: "PATCH", body: { instructor_rate: rate }, version }),
                      })
                    }
                  >
                    <Icon name="edit" size={16} />
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </QueryState>
  );
}

function Card({ card: c, canEdit, edit }: { card: InstructorCard; canEdit: boolean; edit: (e: Editing) => void }) {
  const [open, setOpen] = useState(false);

  return (
    <section aria-label={c.full_name} className="flex flex-col gap-4 rounded-2xl bg-content1 p-4">
      <div>
        <div className="flex items-start justify-between gap-2">
          <h2 className="min-w-0 truncate text-base font-semibold">{c.full_name}</h2>
          {!c.is_active && <span className="shrink-0 rounded-full bg-default-100 px-2 py-0.5 text-xs">нет доступа</span>}
        </div>
        {/* always mounted: once the account is active the button goes, the password modal stays */}
        <ActivateUserButton active={c.is_active} className="mt-2" name={c.full_name} userId={c.id} />
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-sm text-default-500">
          <span>{c.branch_name ?? "Все филиалы"}</span>
          {c.phone && (
            <a className="inline-flex items-center gap-1 text-brand-text" href={telHref(c.phone)}>
              <Icon name="phone" size={14} />
              {c.phone}
            </a>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Number_ hint={`активных: ${c.active_cohorts}`} label="Потоков" value={String(c.cohorts)} />
        <Number_ label="Студентов" value={String(c.students)} />
        <Number_ hint="подтверждённые оплаты" label="Доход с потоков" value={formatPrice(c.income)} />
        <Number_ label="Выплачено" value={formatPrice(c.paid_out)} />
      </div>
      <div className="flex items-center justify-between gap-2 rounded-xl bg-content2 px-3 py-2">
        <div className="min-w-0">
          <div className="text-xs text-default-500">Ставка по умолчанию</div>
          <div className="truncate text-sm font-semibold">{formatPrice(c.default_rate)} в месяц</div>
        </div>
        {canEdit && (
          <Button
            aria-label={`Изменить ставку: ${c.full_name}`}
            size="sm"
            startContent={<Icon name="edit" size={16} />}
            variant="flat"
            onPress={() =>
              edit({
                title: `Ставка: ${c.full_name}`,
                hint: "Подставляется в новые потоки инструктора. Ставки уже созданных потоков не меняются.",
                record: { version: c.version, default_rate: c.default_rate },
                field: "default_rate",
                request: (rate, version) =>
                  api(`/api/v1/instructors/${c.id}`, { method: "PATCH", body: { default_rate: rate }, version }),
              })
            }
          >
            Изменить
          </Button>
        )}
      </div>
      <div>
        <button
          aria-expanded={open}
          className="flex w-full items-center justify-between text-sm font-medium text-brand-text"
          type="button"
          onClick={() => setOpen(!open)}
        >
          Потоки и ставки
          <Icon className={open ? "-rotate-90" : "rotate-90"} name="chevron-right" size={16} />
        </button>
        {open && <Cohorts canEdit={canEdit} edit={edit} id={c.id} />}
      </div>
    </section>
  );
}

export default function InstructorsPage() {
  const canEdit = useCanPaySalaries();
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<Editing | null>(null);

  const list = useQuery({
    queryKey: ["instructor-cards", q],
    queryFn: () => api<{ items: InstructorCard[]; total: number }>("/api/v1/instructors", { params: { q: q.trim() || undefined } }),
  });

  return (
    <>
      <PageHeader actions={<ExportButton params={{ q: q.trim() }} path="/api/v1/instructors/export" />} title="Инструкторы" />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          className="flex-1 md:max-w-xs md:flex-none"
          isClearable
          placeholder="Поиск: имя или телефон"
          startContent={<Icon name="search" size={18} />}
          value={q}
          onClear={() => setQ("")}
          onValueChange={setQ}
        />
      </div>

      <QueryState
        empty={
          <EmptyState
            hint={q.trim() ? "Измените поиск." : "Инструктор — пользователь с ролью «Инструктор»."}
            title={q.trim() ? "Инструкторов не найдено" : "Нет инструкторов"}
          />
        }
        isEmpty={(d) => d.items.length === 0}
        query={list}
        skeleton={<CardGridSkeleton cards={6} />}
      >
        {(d) => (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {d.items.map((c) => (
              <Card key={c.id} canEdit={canEdit} card={c} edit={setEditing} />
            ))}
          </div>
        )}
      </QueryState>

      {editing && (
        <RateModal
          field={editing.field}
          hint={editing.hint}
          record={editing.record}
          request={editing.request}
          title={editing.title}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}
