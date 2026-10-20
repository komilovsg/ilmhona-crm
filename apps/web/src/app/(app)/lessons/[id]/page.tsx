"use client";

import { useCallback, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import { Spinner } from "@heroui/spinner";
import clsx from "clsx";

import { Icon } from "@/components/Icon";
import { useCanMark, useRefreshAttendance } from "@/hooks/attendance";
import { api, isApiError } from "@/lib/api";
import { markedLabel } from "@/lib/attendance";
import { dayTitle, fullDate } from "@/lib/education";
import { notify, notifyError } from "@/lib/toast";
import type { LessonAttendance, MarkRow } from "@/lib/types";

type Cell = { present: boolean; reason: string | null; state: "saving" | "saved" | "error" };

const QUICK_REASONS = ["Болезнь", "Работа", "Семья"];

function Indicator({ cell, onRetry }: { cell: Cell | undefined; onRetry: () => void }) {
  if (!cell) return <span className="h-5 w-24" />;
  if (cell.state === "saving")
    return (
      <span className="flex h-5 items-center gap-1.5 text-xs text-default-500">
        <Spinner size="sm" /> Сохраняю
      </span>
    );
  if (cell.state === "saved")
    return (
      <span aria-live="polite" className="flex h-5 items-center gap-1 text-xs text-success-700 dark:text-success">
        <Icon name="check" size={14} /> Сохранено
      </span>
    );

  return (
    <button
      className="flex h-5 items-center gap-1 text-xs font-medium text-danger underline"
      type="button"
      onClick={onRetry}
    >
      Не сохранено. Повторить
    </button>
  );
}

function Toggle({
  kind,
  active,
  disabled,
  label,
  onPress,
}: {
  kind: "yes" | "no";
  active: boolean;
  disabled: boolean;
  label: string;
  onPress: () => void;
}) {
  const yes = kind === "yes";

  return (
    <button
      aria-label={label}
      aria-pressed={active}
      className={clsx(
        "flex h-12 w-14 items-center justify-center rounded-xl border-2 transition-colors disabled:opacity-60 sm:w-16",
        active
          ? yes
            ? "border-success bg-success text-white"
            : "border-danger bg-danger text-white"
          : yes
            ? "border-default-300 text-default-500 hover:border-success hover:text-success-700 dark:hover:text-success"
            : "border-default-300 text-default-500 hover:border-danger hover:text-danger",
      )}
      disabled={disabled}
      type="button"
      onClick={onPress}
    >
      <Icon name={yes ? "check" : "x"} size={26} strokeWidth={2.6} />
    </button>
  );
}

function StudentRow({
  row,
  cell,
  canMark,
  disabled,
  onMark,
}: {
  row: MarkRow;
  cell: Cell | undefined;
  canMark: boolean;
  disabled: boolean;
  onMark: (present: boolean, reason: string | null) => void;
}) {
  const present = cell ? cell.present : row.present;
  const reason = cell ? cell.reason : row.reason;
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? reason ?? "";
  const saveReason = (text: string) => {
    setDraft(null);
    const next = text.trim() || null;

    if (next !== (reason ?? null)) onMark(false, next);
  };

  return (
    <li className="rounded-2xl bg-content1 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-base font-medium">{row.student_name}</div>
          <Indicator cell={cell} onRetry={() => onMark(present ?? true, reason)} />
        </div>
        <div className="flex shrink-0 gap-2" role="group" aria-label={`Отметка: ${row.student_name}`}>
          <Toggle
            active={present === true}
            disabled={!canMark || disabled}
            kind="yes"
            label={`${row.student_name}: присутствует`}
            onPress={() => onMark(true, null)}
          />
          <Toggle
            active={present === false}
            disabled={!canMark || disabled}
            kind="no"
            label={`${row.student_name}: отсутствует`}
            onPress={() => onMark(false, reason)}
          />
        </div>
      </div>
      {present === false && (
        <div className="mt-3 space-y-2">
          <Input
            aria-label={`Причина отсутствия: ${row.student_name}`}
            isDisabled={!canMark || disabled}
            maxLength={200}
            placeholder="Причина (необязательно)"
            size="sm"
            value={shown}
            onBlur={() => draft !== null && saveReason(draft)}
            onKeyDown={(e) => e.key === "Enter" && saveReason(shown)}
            onValueChange={setDraft}
          />
          {canMark && !disabled && (
            <div className="flex flex-wrap gap-2">
              {QUICK_REASONS.map((r) => (
                <button
                  key={r}
                  className="rounded-full border border-default-300 px-3 py-1 text-xs text-default-600 hover:bg-default-100"
                  type="button"
                  onClick={() => saveReason(r)}
                >
                  {r}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function LessonMark({ data }: { data: LessonAttendance }) {
  const queryClient = useQueryClient();
  const refreshAttendance = useRefreshAttendance();
  const canMark = useCanMark();
  const { lesson } = data;
  const key = ["lesson-attendance", lesson.id];
  const [cells, setCells] = useState<Record<string, Cell>>({});
  const seqs = useRef<Record<string, number>>({});
  const chains = useRef<Record<string, Promise<unknown>>>({});
  const [bulk, setBulk] = useState(false);
  const disabled = lesson.cancelled;

  const patchCache = useCallback(
    (enrollmentId: string, present: boolean, reason: string | null) =>
      queryClient.setQueryData<LessonAttendance>(key, (old) =>
        old
          ? {
              ...old,
              students: old.students.map((s) => (s.enrollment_id === enrollmentId ? { ...s, present, reason } : s)),
            }
          : old,
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, lesson.id],
  );

  // One tap = one request for that one cell, queued behind the previous tap of the same row.
  const mark = (enrollmentId: string, present: boolean, reason: string | null) => {
    const seq = (seqs.current[enrollmentId] = (seqs.current[enrollmentId] ?? 0) + 1);
    const sent = present ? null : reason;

    setCells((c) => ({ ...c, [enrollmentId]: { present, reason: sent, state: "saving" } }));
    const run = async () => {
      try {
        await api(`/api/v1/lessons/${lesson.id}/attendance/${enrollmentId}`, {
          method: "PUT",
          body: { present, reason: sent },
        });
        patchCache(enrollmentId, present, sent);
        void refreshAttendance();
        if (seqs.current[enrollmentId] !== seq) return;
        setCells((c) => ({ ...c, [enrollmentId]: { present, reason: sent, state: "saved" } }));
        setTimeout(() => {
          if (seqs.current[enrollmentId] !== seq) return;
          setCells((c) => {
            const { [enrollmentId]: _gone, ...rest } = c;

            return rest;
          });
        }, 2200);
      } catch (e) {
        if (seqs.current[enrollmentId] !== seq) return;
        setCells((c) => ({ ...c, [enrollmentId]: { present, reason: sent, state: "error" } }));
        if (isApiError(e) && e.status !== 0) notifyError(e);
      }
    };

    chains.current[enrollmentId] = (chains.current[enrollmentId] ?? Promise.resolve()).then(run, run);
  };

  const allPresent = async () => {
    if (bulk) return;
    setBulk(true);
    try {
      const fresh = await api<LessonAttendance>(`/api/v1/lessons/${lesson.id}/attendance/all-present`, {
        method: "POST",
      });

      queryClient.setQueryData(key, fresh);
      setCells({});
      void refreshAttendance();
      notify("Все отмечены присутствующими");
    } catch (e) {
      notifyError(e);
    } finally {
      setBulk(false);
    }
  };

  const effective = data.students.map((s) => (cells[s.enrollment_id] ? cells[s.enrollment_id].present : s.present));
  const marked = effective.filter((p) => p !== null).length;
  const total = data.students.length;

  const nav = (id: string | null, label: string, icon: string) =>
    id ? (
      <Button as={Link} href={`/lessons/${id}`} isIconOnly aria-label={label} variant="flat">
        <Icon name={icon} size={20} />
      </Button>
    ) : (
      <Button isDisabled isIconOnly aria-label={label} variant="flat">
        <Icon name={icon} size={20} />
      </Button>
    );

  return (
    <>
      <Link className="mb-3 inline-flex items-center gap-1 text-sm text-default-500 hover:text-foreground" href="/today">
        <Icon name="chevron-left" size={16} />
        Сегодня
      </Link>

      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-semibold">{lesson.course_name}</h1>
          <p className="text-sm tabular-nums text-default-600">
            {dayTitle(lesson.date)}.{lesson.date.slice(0, 4)} · {lesson.start}–{lesson.end} · {lesson.room_name}
          </p>
          <p className="text-xs text-default-500">
            <Link className="text-brand-text" href={`/cohorts/${lesson.cohort_id}`}>
              {lesson.cohort_code}
            </Link>
            {lesson.number ? ` · урок ${lesson.number} из ${lesson.of}` : ""}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          {nav(data.prev_id, "Предыдущий урок", "chevron-left")}
          {nav(data.next_id, "Следующий урок", "chevron-right")}
        </div>
      </div>

      {lesson.cancelled && (
        <p className="mb-4 rounded-xl bg-danger/10 p-4 text-sm text-danger">Урок отменён: отметки недоступны.</p>
      )}
      {!lesson.cancelled && !lesson.held && (
        <p className="mb-4 rounded-xl bg-warning/15 p-3 text-sm text-default-700">
          Урок ещё не начался: пока он не пройдёт, отметки не попадают в процент посещаемости.
        </p>
      )}

      <div className="mb-4 flex items-center justify-between gap-3">
        <span aria-live="polite" className="text-sm font-medium">
          {markedLabel(marked, total)}
        </span>
        {canMark && !disabled && total > 0 && (
          <Button color="primary" isLoading={bulk} startContent={bulk ? null : <Icon name="check" size={18} />} onPress={() => void allPresent()}>
            Все присутствуют
          </Button>
        )}
      </div>

      {total === 0 ? (
        <p className="rounded-2xl bg-content1 p-8 text-center text-default-500">На этом уроке нет студентов.</p>
      ) : (
        <ul className="space-y-2">
          {data.students.map((s) => (
            <StudentRow
              key={s.enrollment_id}
              canMark={canMark}
              cell={cells[s.enrollment_id]}
              disabled={disabled}
              row={s}
              onMark={(present, reason) => mark(s.enrollment_id, present, reason)}
            />
          ))}
        </ul>
      )}

      <div className="mt-6 flex justify-between gap-3">
        {data.prev_id ? (
          <Button as={Link} href={`/lessons/${data.prev_id}`} variant="flat" startContent={<Icon name="chevron-left" size={18} />}>
            Предыдущий
          </Button>
        ) : (
          <span />
        )}
        {data.next_id && (
          <Button as={Link} href={`/lessons/${data.next_id}`} variant="flat" endContent={<Icon name="chevron-right" size={18} />}>
            Следующий
          </Button>
        )}
      </div>
      <p className="mt-4 text-center text-xs text-default-400">{fullDate(lesson.date)}</p>
    </>
  );
}

export default function LessonPage() {
  const { id } = useParams<{ id: string }>();
  const query = useQuery({
    queryKey: ["lesson-attendance", id],
    queryFn: () => api<LessonAttendance>(`/api/v1/lessons/${id}/attendance`),
  });

  if (query.isPending)
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  if (query.isError || !query.data)
    return (
      <p className="rounded-2xl bg-content1 p-8 text-center text-default-500">
        {isApiError(query.error) && query.error.status === 404 ? "Урок не найден." : "Не удалось загрузить урок."}{" "}
        <Link className="text-brand-text" href="/today">
          Сегодня
        </Link>
      </p>
    );

  // keyed: moving to the previous / next lesson starts with a clean set of in-flight marks
  return <LessonMark key={id} data={query.data} />;
}
