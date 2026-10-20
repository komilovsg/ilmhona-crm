"use client";

import Link from "next/link";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";

import { Icon } from "@/components/Icon";
import { RowMenu } from "@/components/RowMenu";
import type { Stat } from "@/components/StatCards";
import { formatPrice, fullDate } from "@/lib/education";
import { methodLabel, monthLabel, salaryTone } from "@/lib/money";
import type { PayoutRow, SalaryRow, SalarySummary } from "@/lib/money-types";

export function salaryStats(s: SalarySummary): Stat[] {
  return [
    { label: "Фонд за месяц", value: formatPrice(s.fund_month), hint: monthLabel(s.month) },
    { label: "Итого по графику", value: formatPrice(s.total_schedule), hint: "все месяцы потоков" },
    { label: "Выплачено", value: formatPrice(s.paid_total), hint: `в этом месяце: ${formatPrice(s.paid_month)}`, tone: "success" },
    {
      label: "К выплате в этом месяце",
      value: formatPrice(s.due_month),
      hint: Number(s.overdue) > 0 ? `долг за прошлые месяцы: ${formatPrice(s.overdue)}` : undefined,
      tone: Number(s.due_month) > 0 || Number(s.overdue) > 0 ? "danger" : "default",
    },
  ];
}

function StateChip({ state }: { state: string }) {
  return (
    <Chip color={salaryTone(state)} size="sm" variant="flat">
      {state}
    </Chip>
  );
}

type Actions = { onPay: (r: SalaryRow) => void; onRate: (r: SalaryRow) => void };

function RowActions({ r, a }: { r: SalaryRow; a: Actions }) {
  return (
    <div className="flex items-center justify-end gap-1">
      {!r.payout && (
        <Button color="primary" size="sm" startContent={<Icon name="check" size={16} />} variant="flat" onPress={() => a.onPay(r)}>
          Отметить выплату
        </Button>
      )}
      <RowMenu
        actions={[
          ...(r.payout ? [{ key: "pay", label: "Изменить выплату", icon: "edit" }] : []),
          { key: "rate", label: "Изменить ставку потока", icon: "payments" },
        ]}
        label={`Действия: ${r.instructor_name}, ${r.cohort_code}, ${monthLabel(r.period)}`}
        onAction={(k) => (k === "rate" ? a.onRate(r) : a.onPay(r))}
      />
    </div>
  );
}

/** The payout schedule: a table on desktop, cards on a phone. `actions` only for who may pay. */
export function ScheduleList({ rows, actions, showInstructor = true }: { rows: SalaryRow[]; actions?: Actions; showInstructor?: boolean }) {
  return (
    <>
      <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-divider text-xs text-default-500">
            <tr>
              <th className="px-4 py-3 font-medium">Месяц</th>
              {showInstructor && <th className="px-4 py-3 font-medium">Инструктор</th>}
              <th className="px-4 py-3 font-medium">Поток</th>
              <th className="px-4 py-3 font-medium">Ставка</th>
              <th className="px-4 py-3 font-medium">Выплачено</th>
              <th className="px-4 py-3 font-medium">К выплате</th>
              <th className="px-4 py-3 font-medium">Статус</th>
              {actions && <th className="px-4 py-3 text-right font-medium" />}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.cohort_id}-${r.period}`} className="border-b border-divider last:border-0 hover:bg-default-50">
                <td className="whitespace-nowrap px-4 py-3 capitalize">{monthLabel(r.period)}</td>
                {showInstructor && <td className="px-4 py-3 font-medium">{r.instructor_name}</td>}
                <td className="px-4 py-3">
                  <Link className="text-brand-text" href={`/cohorts/${r.cohort_id}`}>
                    {r.cohort_code}
                  </Link>
                  <div className="text-xs text-default-500">{r.course_name}</div>
                </td>
                <td className="whitespace-nowrap px-4 py-3">{formatPrice(r.rate)}</td>
                <td className="whitespace-nowrap px-4 py-3">{formatPrice(r.paid)}</td>
                <td className="whitespace-nowrap px-4 py-3 font-medium">{Number(r.due) > 0 ? formatPrice(r.due) : "—"}</td>
                <td className="px-4 py-3">
                  <StateChip state={r.state} />
                </td>
                {actions && (
                  <td className="px-3 py-2">
                    <RowActions a={actions} r={r} />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="space-y-3 md:hidden">
        {rows.map((r) => (
          <li key={`${r.cohort_id}-${r.period}`} className="rounded-2xl bg-content1 p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="font-medium capitalize">{monthLabel(r.period)}</div>
                <div className="truncate text-sm text-default-500">
                  {showInstructor ? `${r.instructor_name} · ` : ""}
                  <Link className="text-brand-text" href={`/cohorts/${r.cohort_id}`}>
                    {r.cohort_code}
                  </Link>{" "}
                  · {r.course_name}
                </div>
              </div>
              <StateChip state={r.state} />
            </div>
            <dl className="mt-2 grid grid-cols-3 gap-2 text-sm">
              <div>
                <dt className="text-xs text-default-500">Ставка</dt>
                <dd className="font-medium">{formatPrice(r.rate)}</dd>
              </div>
              <div>
                <dt className="text-xs text-default-500">Выплачено</dt>
                <dd className="font-medium">{formatPrice(r.paid)}</dd>
              </div>
              <div>
                <dt className="text-xs text-default-500">К выплате</dt>
                <dd className="font-medium">{Number(r.due) > 0 ? formatPrice(r.due) : "—"}</dd>
              </div>
            </dl>
            {actions && (
              <div className="mt-3">
                <RowActions a={actions} r={r} />
              </div>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

/** Payouts made, newest first. */
export function PayoutsList({ rows, showInstructor = true }: { rows: PayoutRow[]; showInstructor?: boolean }) {
  return (
    <>
      <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-divider text-xs text-default-500">
            <tr>
              <th className="px-4 py-3 font-medium">Дата выплаты</th>
              {showInstructor && <th className="px-4 py-3 font-medium">Инструктор</th>}
              <th className="px-4 py-3 font-medium">Поток</th>
              <th className="px-4 py-3 font-medium">За месяц</th>
              <th className="px-4 py-3 font-medium">Сумма</th>
              <th className="px-4 py-3 font-medium">Способ</th>
              <th className="px-4 py-3 font-medium">Заметка</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} className="border-b border-divider last:border-0 hover:bg-default-50">
                <td className="whitespace-nowrap px-4 py-3 text-default-600">{fullDate(p.paid_at)}</td>
                {showInstructor && <td className="px-4 py-3 font-medium">{p.instructor_name}</td>}
                <td className="px-4 py-3">
                  <Link className="text-brand-text" href={`/cohorts/${p.cohort_id}`}>
                    {p.cohort_code}
                  </Link>
                </td>
                <td className="px-4 py-3 capitalize">{monthLabel(p.period)}</td>
                <td className="whitespace-nowrap px-4 py-3 font-medium">{formatPrice(p.amount)}</td>
                <td className="px-4 py-3">{methodLabel(p.method)}</td>
                <td className="px-4 py-3 text-default-600">{p.note ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="space-y-3 md:hidden">
        {rows.map((p) => (
          <li key={p.id} className="rounded-2xl bg-content1 p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="font-medium capitalize">{monthLabel(p.period)}</div>
                <div className="truncate text-sm text-default-500">
                  {showInstructor ? `${p.instructor_name} · ` : ""}
                  {p.cohort_code} · {p.course_name}
                </div>
              </div>
              <span className="shrink-0 font-semibold">{formatPrice(p.amount)}</span>
            </div>
            <div className="mt-1 text-sm text-default-500">
              {fullDate(p.paid_at)} · {methodLabel(p.method)}
              {p.note ? ` · ${p.note}` : ""}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
