"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Spinner } from "@heroui/spinner";
import clsx from "clsx";

import { ConflictDialog } from "@/components/ConflictDialog";
import { Icon } from "@/components/Icon";
import { EmptyState, QueryState } from "@/components/QueryState";
import { ListSkeleton } from "@/components/Skeletons";
import { PersonStatus } from "@/components/StatusChip";
import { useRefreshAttendance } from "@/hooks/attendance";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import { GRADE_MAX, PASS_TOTAL, parseGrade, percentLabel } from "@/lib/attendance";
import type { GradeRow } from "@/lib/types";

type Field = "homework" | "final";
type Saved = "idle" | "saving" | "saved" | "error";

const text = (n: number | null) => (n === null ? "" : String(n));

function ScoreInput({
  label,
  value,
  disabled,
  invalid,
  onFocus,
  onChange,
  onCommit,
}: {
  label: string;
  value: string;
  disabled: boolean;
  invalid: boolean;
  onFocus: () => void;
  onChange: (value: string) => void;
  onCommit: () => void;
}) {
  return (
    <input
      aria-invalid={invalid}
      aria-label={label}
      className={clsx(
        "h-11 w-20 rounded-lg border bg-content2 px-3 text-center text-base tabular-nums outline-none focus:border-primary disabled:opacity-60 md:h-9",
        invalid ? "border-danger" : "border-default-300",
      )}
      disabled={disabled}
      inputMode="numeric"
      maxLength={2}
      placeholder={`0–${GRADE_MAX}`}
      value={value}
      onBlur={onCommit}
      onChange={(e) => onChange(e.target.value)}
      onFocus={onFocus}
      onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
    />
  );
}

function Total({ row }: { row: GradeRow }) {
  return (
    <span
      className={clsx(
        "inline-flex min-w-14 justify-center rounded-lg px-2.5 py-1 text-base font-semibold tabular-nums",
        row.passed ? "bg-success/15 text-success-700 dark:text-success" : "bg-default-100",
      )}
      title={row.passed ? `Проходной балл ${PASS_TOTAL} набран` : `До проходного балла ${PASS_TOTAL}: ${PASS_TOTAL - row.total}`}
    >
      {row.total}
    </span>
  );
}

type GradeValues = { homework: number | null; final: number | null };

const fieldValue = (draft: string, fallback: number | null) => {
  const parsed = parseGrade(draft);

  return parsed.ok ? parsed.value : fallback;
};

/**
 * One student: Д/З and финал inputs. Each saves on blur through `useVersionedSave` (#25): the
 * version of the grade goes in `If-Match`, and a 409 opens the shared conflict dialog, where
 * «Обновить и повторить» keeps the typed value on top of what the other user saved. A save made
 * while another is still in flight waits for it, so two quick edits never conflict with each other.
 */
function useGradeRow(cohortId: string, row: GradeRow) {
  const queryClient = useQueryClient();
  const refreshAttendance = useRefreshAttendance();
  const [draft, setDraft] = useState<Record<Field, string>>({ homework: text(row.homework), final: text(row.final) });
  const [seen, setSeen] = useState({ homework: row.homework, final: row.final });
  const [focus, setFocus] = useState<Field | null>(null);
  const [invalid, setInvalid] = useState<Field | null>(null);
  const [saved, setSaved] = useState<Saved>("idle");
  const queued = useRef<GradeValues | null>(null);
  const key = ["grades", cohortId];
  const values: GradeValues = {
    homework: fieldValue(draft.homework, row.homework),
    final: fieldValue(draft.final, row.final),
  };

  // the server's values changed (a save, a refetch): refresh every field that is not being typed in
  if (row.homework !== seen.homework || row.final !== seen.final) {
    setSeen({ homework: row.homework, final: row.final });
    setDraft((d) => ({
      homework: focus === "homework" ? d.homework : text(row.homework),
      final: focus === "final" ? d.final : text(row.final),
    }));
  }

  const edit = useVersionedSave<GradeRow, GradeValues>({
    record: row,
    values,
    toValues: (r) => ({ homework: r.homework, final: r.final }),
    apply: (v) => setDraft({ homework: text(v.homework), final: text(v.final) }),
    request: (changed, version) =>
      api<GradeRow>(`/api/v1/enrollments/${row.enrollment_id}/grade`, { method: "PATCH", body: changed, version }),
    labels: { homework: "Д/З", final: "Финал" },
    onSaved: (result) => {
      if (result) {
        const out = result as GradeRow;

        queryClient.setQueryData<GradeRow[]>(key, (rows) =>
          rows?.map((r) => (r.enrollment_id === out.enrollment_id ? { ...r, ...out } : r)),
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

  const commit = (field: Field) => {
    setFocus(null);
    if (!parseGrade(draft[field]).ok) {
      setInvalid(field);

      return;
    }
    setInvalid(null);
    setSaved("saving");
    if (edit.pending) queued.current = values;
    else void edit.save(values);
  };

  const shown: Saved = edit.error ? "error" : edit.pending ? "saving" : saved;

  return { draft, setDraft, setFocus, invalid, saved: shown, commit, edit };
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

/** Remounts the editor after «Отменить» in the conflict dialog, so it starts from the fresh record. */
function RowFields(props: { row: GradeRow; canMark: boolean; cohortId: string; layout: "table" | "card" }) {
  const [epoch, setEpoch] = useState(0);

  return <RowEditor key={epoch} {...props} onDiscard={() => setEpoch((e) => e + 1)} />;
}

function RowEditor({
  row,
  canMark,
  cohortId,
  layout,
  onDiscard,
}: {
  row: GradeRow;
  canMark: boolean;
  cohortId: string;
  layout: "table" | "card";
  onDiscard: () => void;
}) {
  const queryClient = useQueryClient();
  const g = useGradeRow(cohortId, row);
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
  const input = (field: Field, label: string) =>
    canMark ? (
      <ScoreInput
        disabled={false}
        invalid={g.invalid === field}
        label={`${label}: ${row.student_name}`}
        value={g.draft[field]}
        onChange={(v) => g.setDraft((d) => ({ ...d, [field]: v }))}
        onCommit={() => g.commit(field)}
        onFocus={() => g.setFocus(field)}
      />
    ) : (
      <span className="tabular-nums">{row[field] ?? "—"}</span>
    );
  const attendance = (
    <span className="tabular-nums" title={`${row.present} из ${row.held} проведённых, ${percentLabel(row.percent)}`}>
      {row.attendance_score}
      <span className="text-default-400"> / 20</span>
    </span>
  );

  if (layout === "table")
    return (
      <>
        <td className="px-4 py-3">
          {attendance}
          <div className="text-xs text-default-500">
            {percentLabel(row.percent)}
            {row.unmarked > 0 && <span className="text-secondary"> · не отмечено {row.unmarked}</span>}
          </div>
        </td>
        <td className="px-4 py-3">{input("homework", "Д/З")}</td>
        <td className="px-4 py-3">{input("final", "Финал")}</td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <Total row={row} />
            <SavedMark saved={g.saved} />
          </div>
          {g.edit.error && <p className="mt-1 text-xs text-danger">{g.edit.error}</p>}
          {dialog}
        </td>
      </>
    );

  return (
    <div className="mt-3 space-y-3">
      <div className="flex items-center justify-between text-sm">
        <span className="text-default-500">Посещаемость</span>
        <span>
          {attendance}
          <span className="ml-2 text-xs text-default-500">
            {percentLabel(row.percent)}
            {row.unmarked > 0 && <span className="text-secondary"> · не отмечено {row.unmarked}</span>}
          </span>
        </span>
      </div>
      <div className="flex items-center justify-between text-sm">
        <label className="text-default-500">Д/З (0–{GRADE_MAX})</label>
        {input("homework", "Д/З")}
      </div>
      <div className="flex items-center justify-between text-sm">
        <label className="text-default-500">Финал (0–{GRADE_MAX})</label>
        {input("final", "Финал")}
      </div>
      <div className="flex items-center justify-between border-t border-divider pt-3 text-sm">
        <span className="font-medium">Итого</span>
        <span className="flex items-center gap-2">
          <Total row={row} />
          <SavedMark saved={g.saved} />
        </span>
      </div>
      {g.edit.error && <p className="text-xs text-danger">{g.edit.error}</p>}
      {dialog}
    </div>
  );
}

export function GradesTab({ cohortId, canMark }: { cohortId: string; canMark: boolean }) {
  const list = useQuery({
    queryKey: ["grades", cohortId],
    queryFn: () => api<GradeRow[]>(`/api/v1/cohorts/${cohortId}/grades`),
  });

  return (
    <QueryState
      empty={<EmptyState title="В потоке пока нет студентов" />}
      errorText="Не удалось загрузить оценки"
      isEmpty={(rows) => rows.length === 0}
      query={list}
      skeleton={<ListSkeleton cols={6} rows={6} />}
    >
      {(rows) => <GradesList canMark={canMark} cohortId={cohortId} rows={rows} />}
    </QueryState>
  );
}

function GradesList({ cohortId, canMark, rows }: { cohortId: string; canMark: boolean; rows: GradeRow[] }) {
  return (
    <>
      <p className="mb-3 text-xs text-default-500">
        Итог = посещаемость (до 20, считается сама) + Д/З (до {GRADE_MAX}) + финал (до {GRADE_MAX}). От {PASS_TOTAL}{" "}
        баллов студент станет выпускником, когда поток закончится.
      </p>
      <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-divider text-xs text-default-500">
            <tr>
              <th className="px-4 py-3 font-medium">Студент</th>
              <th className="px-4 py-3 font-medium">Посещаемость</th>
              <th className="px-4 py-3 font-medium">Д/З</th>
              <th className="px-4 py-3 font-medium">Финал</th>
              <th className="px-4 py-3 font-medium">Итого</th>
              <th className="px-4 py-3 font-medium">Статус</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <GradeTableRow key={r.enrollment_id} canMark={canMark} cohortId={cohortId} row={r} />
            ))}
          </tbody>
        </table>
      </div>
      <ul className="space-y-3 md:hidden">
        {rows.map((r) => (
          <li key={r.enrollment_id} className="rounded-2xl bg-content1 p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{r.student_name}</span>
              <PersonStatus status={r.status} />
            </div>
            <RowFields canMark={canMark} cohortId={cohortId} layout="card" row={r} />
          </li>
        ))}
      </ul>
    </>
  );
}

function GradeTableRow({ row, canMark, cohortId }: { row: GradeRow; canMark: boolean; cohortId: string }) {
  return (
    <tr className="border-b border-divider last:border-0 hover:bg-default-50">
      <td className="px-4 py-3 font-medium">{row.student_name}</td>
      <RowFields canMark={canMark} cohortId={cohortId} layout="table" row={row} />
      <td className="px-4 py-3">
        <PersonStatus status={row.status} />
      </td>
    </tr>
  );
}
