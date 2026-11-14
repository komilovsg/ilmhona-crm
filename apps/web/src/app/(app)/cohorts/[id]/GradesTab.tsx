"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Spinner } from "@heroui/spinner";
import clsx from "clsx";

import { GradingPanel } from "./GradingPanel";

import { ConflictDialog } from "@/components/ConflictDialog";
import { Icon } from "@/components/Icon";
import { EmptyState, QueryState } from "@/components/QueryState";
import { ListSkeleton } from "@/components/Skeletons";
import { PersonStatus } from "@/components/StatusChip";
import { ExportButton } from "@/components/ExportButton";
import { useRefreshAttendance } from "@/hooks/attendance";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api, messageOf } from "@/lib/api";
import { percentLabel } from "@/lib/attendance";
import { parseScore } from "@/lib/grading";
import type { GradeRow, GradesData } from "@/lib/types";

type Saved = "idle" | "saving" | "saved" | "error";
type Scheme = GradesData["scheme"];
type Manual = Scheme["categories"][number];
type ScoreValues = Record<string, number | null>;

const text = (n: number | null | undefined) => (n === null || n === undefined ? "" : String(n));

/** The manual categories of the scheme: the columns a teacher fills in. */
const manualOf = (scheme: Scheme) => scheme.categories.filter((c) => c.kind === "manual");

function ScoreInput({
  category,
  student,
  value,
  stored,
  invalid,
  onFocus,
  onChange,
  onCommit,
}: {
  category: Manual;
  student: string;
  value: string;
  /** The saved score: above a weight lowered later it counts as the weight. */
  stored: number | undefined;
  invalid: boolean;
  onFocus: () => void;
  onChange: (value: string) => void;
  onCommit: () => void;
}) {
  return (
    <span className="inline-flex flex-col items-center">
      <input
        aria-describedby={invalid ? `hint-${category.key}-${student}` : undefined}
        aria-invalid={invalid}
        aria-label={`${category.name}: ${student}`}
        className={clsx(
          "h-11 w-20 rounded-lg border bg-content2 px-3 text-center text-base tabular-nums outline-none focus:border-primary disabled:opacity-60 md:h-9",
          invalid ? "border-danger" : "border-default-300",
        )}
        inputMode="numeric"
        maxLength={3}
        placeholder={`0–${category.weight}`}
        value={value}
        onBlur={onCommit}
        onChange={(e) => onChange(e.target.value)}
        onFocus={onFocus}
        onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
      />
      {invalid && (
        <span className="mt-0.5 text-xs text-danger" id={`hint-${category.key}-${student}`}>
          Не больше {category.weight}
        </span>
      )}
      {!invalid && <Capped stored={stored} weight={category.weight} />}
    </span>
  );
}

/** «больше максимума, засчитано 30»: a score entered before its weight was lowered. */
function Capped({ stored, weight }: { stored: number | undefined; weight: number }) {
  if (stored === undefined || stored <= weight) return null;

  return (
    <span
      className="mt-0.5 whitespace-nowrap rounded-md bg-warning/15 px-1.5 text-xs text-warning-700 dark:text-warning"
      title={`Не больше ${weight}: максимум категории уменьшили после того, как балл поставили`}
    >
      {stored} → {weight}, больше максимума
    </span>
  );
}

function Total({ row, pass }: { row: GradeRow; pass: number }) {
  return (
    <span className="inline-flex flex-col items-start">
      <span
        className={clsx(
          "inline-flex min-w-14 justify-center rounded-lg px-2.5 py-1 text-base font-semibold tabular-nums",
          row.passed ? "bg-success/15 text-success-700 dark:text-success" : "bg-default-100",
        )}
        title={row.passed ? `Проходной балл ${pass} набран` : `До проходного балла ${pass}: ${pass - row.total}`}
      >
        {row.total}
      </span>
      {row.projected !== null && row.projected !== row.total && (
        <span className="mt-0.5 text-xs text-default-500" title="Итог, если остальное пойдёт так же, как уже выставленное">
          прогноз {row.projected}
        </span>
      )}
    </span>
  );
}

function PassChip({ row }: { row: GradeRow }) {
  return (
    <span
      className={clsx(
        "whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium",
        row.passed ? "bg-success/15 text-success-700 dark:text-success" : "bg-default-100 text-default-600",
      )}
    >
      {row.passed ? "проходит" : "не набрал"}
    </span>
  );
}

/**
 * One student: an input per manual category of the cohort's scheme. Each saves on blur through
 * `useVersionedSave` (#25): the version of the grade goes in `X-Record-Version`, and a 409 opens
 * the shared conflict dialog. A save made while another is still in flight waits for it.
 */
function useGradeRow(cohortId: string, row: GradeRow, manual: Manual[]) {
  const queryClient = useQueryClient();
  const refreshAttendance = useRefreshAttendance();
  const keys = manual.map((c) => c.key);
  const fromRow = (r: GradeRow): ScoreValues => Object.fromEntries(keys.map((k) => [k, r.scores[k] ?? null]));
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(keys.map((k) => [k, text(row.scores[k])])),
  );
  const [seen, setSeen] = useState(JSON.stringify(fromRow(row)));
  const [focus, setFocus] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [saved, setSaved] = useState<Saved>("idle");
  const queued = useRef<ScoreValues | null>(null);
  const key = ["grades", cohortId];
  const max = Object.fromEntries(manual.map((c) => [c.key, c.weight]));
  const values: ScoreValues = Object.fromEntries(
    keys.map((k) => {
      const parsed = parseScore(draft[k] ?? "", max[k]);

      return [k, parsed.ok ? parsed.value : (row.scores[k] ?? null)];
    }),
  );

  // the server's values changed (a save, a refetch): refresh every field that is not being typed in
  const now = JSON.stringify(fromRow(row));

  if (now !== seen) {
    setSeen(now);
    setDraft((d) => Object.fromEntries(keys.map((k) => [k, focus === k ? (d[k] ?? "") : text(row.scores[k])])));
  }

  const edit = useVersionedSave<GradeRow, ScoreValues>({
    record: row,
    values,
    toValues: fromRow,
    apply: (v) => setDraft(Object.fromEntries(keys.map((k) => [k, text(v[k])]))),
    request: (changed, version) =>
      api<GradeRow>(`/api/v1/enrollments/${row.enrollment_id}/grade`, {
        method: "PATCH",
        body: { scores: changed },
        version,
      }),
    labels: Object.fromEntries(manual.map((c) => [c.key, c.name])),
    onSaved: (result) => {
      if (result) {
        const out = result as GradeRow;

        queryClient.setQueryData<GradesData>(key, (data) =>
          data
            ? { ...data, rows: data.rows.map((r) => (r.enrollment_id === out.enrollment_id ? { ...r, ...out } : r)) }
            : data,
        );
        setSaved("saved");
        void refreshAttendance();
      }
    },
  });

  // run the save that waited for the previous one (with the fresh version of that one)
  useEffect(() => {
    const next = queued.current;

    if (next && !edit.pending) {
      queued.current = null;
      void edit.save(next);
    }
  }, [edit]);

  const commit = (field: string) => {
    setFocus(null);
    if (!parseScore(draft[field] ?? "", max[field]).ok) {
      setInvalid(field);

      return;
    }
    setInvalid(null);
    setSaved("saving");
    if (edit.pending) queued.current = values;
    else void edit.save(values);
  };

  const error = edit.failure ? messageOf(edit.failure) : null;
  const shown: Saved = error ? "error" : edit.pending ? "saving" : saved;

  return { draft, setDraft, setFocus, invalid, saved: shown, commit, edit, error };
}

function SavedMark({ saved }: { saved: Saved }) {
  return (
    <span aria-live="polite" className="inline-flex h-5 w-5 items-center justify-center">
      {saved === "saving" && <Spinner size="sm" />}
      {saved === "saved" && <Icon className="text-success" name="check" size={16} />}
      {saved === "error" && <Icon className="text-danger" name="x" size={16} />}
    </span>
  );
}

type RowProps = { row: GradeRow; canMark: boolean; cohortId: string; scheme: Scheme; layout: "table" | "card" };

/** Remounts the editor after «Отменить» in the conflict dialog, so it starts from the fresh record. */
function RowFields(props: RowProps) {
  const [epoch, setEpoch] = useState(0);

  return <RowEditor key={epoch} {...props} onDiscard={() => setEpoch((e) => e + 1)} />;
}

function RowEditor({ row, canMark, cohortId, scheme, layout, onDiscard }: RowProps & { onDiscard: () => void }) {
  const queryClient = useQueryClient();
  const manual = manualOf(scheme);
  const attendanceCat = scheme.categories.find((c) => c.kind === "attendance");
  const g = useGradeRow(cohortId, row, manual);
  const dialog = (
    <ConflictDialog
      save={{
        ...g.edit,
        cancel: () => {
          g.edit.cancel();
          void queryClient.invalidateQueries({ queryKey: ["grades", cohortId] });
          onDiscard();
        },
      }}
    />
  );
  const input = (c: Manual) =>
    canMark ? (
      <ScoreInput
        category={c}
        invalid={g.invalid === c.key}
        stored={row.scores[c.key]}
        student={row.student_name}
        value={g.draft[c.key] ?? ""}
        onChange={(v) => g.setDraft((d) => ({ ...d, [c.key]: v }))}
        onCommit={() => g.commit(c.key)}
        onFocus={() => g.setFocus(c.key)}
      />
    ) : (
      <span className="inline-flex flex-col items-start tabular-nums">
        {row.scores[c.key] ?? "—"}
        <Capped stored={row.scores[c.key]} weight={c.weight} />
      </span>
    );
  const attendance = (
    <span className="tabular-nums" title={`${row.present} из ${row.held} проведённых, ${percentLabel(row.percent)}`}>
      {row.attendance_score}
      <span className="text-default-400"> / {attendanceCat?.weight ?? 0}</span>
    </span>
  );
  const attendanceNote = (
    <>
      {percentLabel(row.percent)}
      {row.unmarked > 0 && <span className="text-secondary"> · не отмечено {row.unmarked}</span>}
    </>
  );

  if (layout === "table")
    return (
      <>
        <td className="px-4 py-3">
          {attendance}
          <div className="text-xs text-default-500">{attendanceNote}</div>
        </td>
        {manual.map((c) => (
          <td key={c.key} className="px-4 py-3">
            {input(c)}
          </td>
        ))}
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <Total pass={scheme.pass_score} row={row} />
            <SavedMark saved={g.saved} />
          </div>
          {g.error && <p className="mt-1 text-xs text-danger">{g.error}</p>}
          {dialog}
        </td>
        <td className="px-4 py-3">
          <PassChip row={row} />
        </td>
      </>
    );

  return (
    <div className="mt-3 space-y-3">
      <div className="flex items-center justify-between text-sm">
        <span className="text-default-500">{attendanceCat?.name ?? "Посещаемость"} · авто</span>
        <span>
          {attendance}
          <span className="ml-2 text-xs text-default-500">{attendanceNote}</span>
        </span>
      </div>
      {manual.map((c) => (
        <div key={c.key} className="flex items-center justify-between gap-3 text-sm">
          <label className="text-default-500">
            {c.name} · {c.weight}
          </label>
          {input(c)}
        </div>
      ))}
      <div className="flex items-center justify-between border-t border-divider pt-3 text-sm">
        <span className="flex items-center gap-2 font-medium">
          Итого <PassChip row={row} />
        </span>
        <span className="flex items-center gap-2">
          <Total pass={scheme.pass_score} row={row} />
          <SavedMark saved={g.saved} />
        </span>
      </div>
      {g.error && <p className="text-xs text-danger">{g.error}</p>}
      {dialog}
    </div>
  );
}

export function GradesTab({ cohortId, canMark }: { cohortId: string; canMark: boolean }) {
  const list = useQuery({
    queryKey: ["grades", cohortId],
    queryFn: () => api<GradesData>(`/api/v1/cohorts/${cohortId}/grades`),
  });

  return (
    <>
      <GradingPanel cohortId={cohortId} />
      <QueryState
        empty={<EmptyState title="В потоке пока нет студентов" />}
        errorText="Не удалось загрузить оценки"
        isEmpty={(data) => data.rows.length === 0}
        query={list}
        skeleton={<ListSkeleton cols={6} rows={6} />}
      >
        {(data) => <GradesList canMark={canMark} cohortId={cohortId} data={data} />}
      </QueryState>
    </>
  );
}

function GradesList({ cohortId, canMark, data }: { cohortId: string; canMark: boolean; data: GradesData }) {
  const { scheme, rows } = data;
  const manual = manualOf(scheme);
  const attendanceCat = scheme.categories.find((c) => c.kind === "attendance");
  // the inputs of a row belong to the scheme they were made for: a scheme change remounts them
  const schemeKey = scheme.categories.map((c) => `${c.key}:${c.weight}`).join("|");

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-default-500">
          Итог = сумма баллов по категориям шкалы потока (посещаемость считается сама). От {scheme.pass_score} баллов
          студент станет выпускником, когда поток закончится. Прогноз — итог, если остальное пойдёт так же.
        </p>
        <ExportButton label="Оценки" path={`/api/v1/cohorts/${cohortId}/grades/export`} />
      </div>
      <div className="hidden overflow-x-auto rounded-2xl bg-content1 md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-divider text-xs text-default-500">
            <tr>
              <th className="px-4 py-3 font-medium">Студент</th>
              <th className="px-4 py-3 font-medium">
                {attendanceCat?.name ?? "Посещаемость"} · {attendanceCat?.weight ?? 0}
                <span className="ml-1 font-normal text-default-400">авто</span>
              </th>
              {manual.map((c) => (
                <th key={c.key} className="px-4 py-3 font-medium" title={`Не больше ${c.weight}`}>
                  {c.name} · {c.weight}
                </th>
              ))}
              <th className="px-4 py-3 font-medium">Итого</th>
              <th className="px-4 py-3 font-medium">Зачёт</th>
              <th className="px-4 py-3 font-medium">Статус</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.enrollment_id}-${schemeKey}`} className="border-b border-divider last:border-0 hover:bg-default-50">
                <td className="px-4 py-3 font-medium">{r.student_name}</td>
                <RowFields canMark={canMark} cohortId={cohortId} layout="table" row={r} scheme={scheme} />
                <td className="px-4 py-3">
                  <PersonStatus status={r.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul data-rows className="space-y-3 md:hidden">
        {rows.map((r) => (
          <li key={`${r.enrollment_id}-${schemeKey}`} className="rounded-2xl bg-content1 p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{r.student_name}</span>
              <PersonStatus status={r.status} />
            </div>
            <RowFields canMark={canMark} cohortId={cohortId} layout="card" row={r} scheme={scheme} />
          </li>
        ))}
      </ul>
    </>
  );
}
