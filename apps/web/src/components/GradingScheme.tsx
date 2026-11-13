"use client";

import { useRef, useState } from "react";
import { Button } from "@heroui/button";
import clsx from "clsx";

import { AppModal } from "./AppModal";
import { ConfirmModal } from "./ConfirmModal";
import { ConflictDialog } from "./ConflictDialog";
import { ExportButton } from "./ExportButton";
import { Icon } from "./Icon";
import { LoadingButton } from "./LoadingButton";

import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api, messageOf, uploadCsv } from "@/lib/api";
import {
  KIND_LABEL,
  MAX_CATEGORIES,
  TARGETS,
  TOTAL,
  move,
  newCategoryName,
  parsePercent,
  schemeProblems,
  schemeSum,
  weightsLabel,
  type Category,
  type SchemeFields,
} from "@/lib/grading";
import { notify, notifyError } from "@/lib/toast";

/** What both `GET /grading/standard` and `GET /cohorts/{id}/grading` answer. */
export type SchemePayload = {
  version: number;
  scheme: SchemeFields;
  can_edit: boolean;
  source?: "standard" | "cohort";
  archived?: { key: string; name: string; scores: number }[];
  completed?: boolean;
};

type Values = SchemeFields;

const toValues = (r: SchemePayload): Values => ({
  categories: r.scheme.categories,
  pass_score: r.scheme.pass_score,
  target_retention: r.scheme.target_retention,
  target_attendance: r.scheme.target_attendance,
  target_pass_rate: r.scheme.target_pass_rate,
});

const LABELS: Partial<Record<keyof Values, string>> = {
  categories: "Категории и баллы",
  ...Object.fromEntries(TARGETS.map((t) => [t.key, t.label])),
};

/** A read-only line of the scheme: «Посещаемость 20 (авто) · Домашние задания 40 · …». */
export function SchemeChips({ scheme }: { scheme: SchemeFields }) {
  return (
    <div className="flex flex-wrap gap-2">
      {scheme.categories.map((c) => (
        <span
          key={c.key ?? c.name}
          className="inline-flex items-center gap-1.5 rounded-lg bg-default-100 px-2.5 py-1 text-sm"
          title={c.kind === "attendance" ? "Считается сама из посещаемости" : "Ставит преподаватель"}
        >
          {c.name}
          <span className="font-semibold tabular-nums">{c.weight}</span>
          {c.kind === "attendance" && <span className="text-xs text-default-500">авто</span>}
        </span>
      ))}
    </div>
  );
}

export function SchemeTargets({ scheme }: { scheme: SchemeFields }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
      {TARGETS.map((t) => (
        <div key={t.key}>
          <dt className="text-xs text-default-500">{t.label}</dt>
          <dd className="font-semibold tabular-nums">{scheme[t.key]}</dd>
        </div>
      ))}
    </dl>
  );
}

function NumberInput({
  label,
  value,
  onChange,
  invalid,
  hint,
  className,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  invalid?: boolean;
  hint?: string;
  className?: string;
}) {
  const [text, setText] = useState(String(value));
  const [seen, setSeen] = useState(value);

  if (seen !== value) {
    setSeen(value);
    if (parsePercent(text) !== value) setText(String(value));
  }
  const bad = invalid || parsePercent(text) === null;

  return (
    <input
      aria-invalid={bad}
      aria-label={label}
      className={clsx(
        "h-11 w-20 rounded-lg border bg-content2 px-3 text-center text-base tabular-nums outline-none focus:border-primary md:h-9",
        bad ? "border-danger" : "border-default-300",
        className,
      )}
      inputMode="numeric"
      maxLength={3}
      title={hint}
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        const n = parsePercent(e.target.value);

        onChange(n ?? Number.NaN);
      }}
    />
  );
}

/**
 * The scheme editor: ordered categories (name, points, авто / вручную), a live «Сумма: 100 из 100»,
 * the pass score and the targets. Saving is the caller's (`onSave` gets the whole draft).
 */
export function SchemeEditor({
  initial,
  saving,
  onSave,
  onCancel,
}: {
  initial: SchemeFields;
  saving: boolean;
  onSave: (draft: SchemeFields) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<SchemeFields>(initial);
  const sum = schemeSum(draft.categories);
  const problems = schemeProblems(draft.categories);
  const badTargets = TARGETS.some((t) => !Number.isInteger(draft[t.key]));
  const setCategory = (i: number, patch: Partial<Category>) =>
    setDraft((d) => ({ ...d, categories: d.categories.map((c, j) => (j === i ? { ...c, ...patch } : c)) }));

  return (
    <div className="space-y-5">
      <section aria-label="Категории">
        <div className="mb-2 flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium">Категории</h3>
          <span
            aria-live="polite"
            className={clsx(
              "rounded-lg px-2.5 py-1 text-sm font-semibold tabular-nums",
              sum === TOTAL ? "bg-success/15 text-success-700 dark:text-success" : "bg-danger/10 text-danger",
            )}
          >
            Сумма: {Number.isNaN(sum) ? "—" : sum} из {TOTAL}
          </span>
        </div>
        <ul className="space-y-2">
          {draft.categories.map((c, i) => (
            <li key={c.key ?? `new-${i}`} className="flex flex-wrap items-center gap-2 rounded-xl bg-content2/60 p-2 sm:flex-nowrap">
              <div className="flex flex-col">
                <Button
                  isIconOnly
                  aria-label={`Выше: ${c.name}`}
                  className="h-5 min-w-6"
                  isDisabled={i === 0}
                  size="sm"
                  variant="light"
                  onPress={() => setDraft((d) => ({ ...d, categories: move(d.categories, i, -1) }))}
                >
                  <Icon className="rotate-90" name="chevron-left" size={14} />
                </Button>
                <Button
                  isIconOnly
                  aria-label={`Ниже: ${c.name}`}
                  className="h-5 min-w-6"
                  isDisabled={i === draft.categories.length - 1}
                  size="sm"
                  variant="light"
                  onPress={() => setDraft((d) => ({ ...d, categories: move(d.categories, i, 1) }))}
                >
                  <Icon className="-rotate-90" name="chevron-left" size={14} />
                </Button>
              </div>
              <input
                aria-label="Название категории"
                className="h-11 min-w-0 flex-1 rounded-lg border border-default-300 bg-content2 px-3 text-base outline-none focus:border-primary md:h-9 md:text-sm"
                maxLength={60}
                value={c.name}
                onChange={(e) => setCategory(i, { name: e.target.value })}
              />
              <NumberInput
                hint={c.kind === "attendance" ? "0–100" : "1–100"}
                label={`Баллы: ${c.name}`}
                value={c.weight}
                onChange={(n) => setCategory(i, { weight: n })}
              />
              <span
                className={clsx(
                  "w-20 rounded-md px-2 py-1 text-center text-xs",
                  c.kind === "attendance" ? "bg-primary/10 text-brand-text" : "bg-default-100 text-default-600",
                )}
                title={c.kind === "attendance" ? "Считается сама: баллы × присутствовал ÷ проведено" : "Ставит преподаватель"}
              >
                {KIND_LABEL[c.kind]}
              </span>
              {c.kind === "manual" ? (
                <Button
                  isIconOnly
                  aria-label={`Убрать категорию ${c.name}`}
                  size="sm"
                  variant="light"
                  onPress={() => setDraft((d) => ({ ...d, categories: d.categories.filter((_, j) => j !== i) }))}
                >
                  <Icon name="trash" size={16} />
                </Button>
              ) : (
                <span className="w-8" />
              )}
            </li>
          ))}
        </ul>
        <Button
          className="mt-2"
          isDisabled={draft.categories.length >= MAX_CATEGORIES}
          size="sm"
          startContent={<Icon name="plus" size={16} />}
          variant="flat"
          onPress={() =>
            setDraft((d) => ({
              ...d,
              categories: [...d.categories, { name: newCategoryName(d.categories), weight: 0, kind: "manual" }],
            }))
          }
        >
          Добавить категорию
        </Button>
        {problems.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm text-danger" role="alert">
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="Проходной балл и цели" className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {TARGETS.map((t) => (
          <label key={t.key} className="flex flex-col gap-1 text-sm">
            <span className="text-default-500">{t.label}</span>
            <NumberInput hint={t.hint} label={t.label} value={draft[t.key]} onChange={(n) => setDraft((d) => ({ ...d, [t.key]: n }))} />
          </label>
        ))}
      </section>
      <div className="flex justify-end gap-2">
        <Button variant="light" onPress={onCancel}>
          Отмена
        </Button>
        <LoadingButton
          color="primary"
          isDisabled={problems.length > 0 || badTargets}
          isLoading={saving}
          onPress={() => onSave({ ...draft, categories: draft.categories.map((c) => ({ ...c, name: c.name.trim() })) })}
        >
          Сохранить
        </LoadingButton>
      </div>
    </div>
  );
}

type Preview = Omit<SchemeFields, "categories"> & {
  categories: (Category & { row: number })[];
  sum: number;
  errors: { row: number | null; message: string }[];
  ok: boolean;
};

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

/**
 * Saving a scheme: versioned PATCH (#25, the conflict dialog), and a confirmation when a removed
 * category has scores (409 `grading_scores_archived`: they are kept in the archive, the user says
 * so first, then the same values go again with `confirm_archive`).
 */
export function useSchemeSave(path: string, record: SchemePayload, onSaved: (result: SchemePayload) => void) {
  const confirmed = useRef(false);
  const last = useRef<Values | null>(null);
  const [dismissed, setDismissed] = useState<unknown>(null);
  const save = useVersionedSave<SchemePayload, Values>({
    record,
    values: toValues(record),
    toValues,
    apply: () => undefined,
    request: (changed, version) =>
      api<SchemePayload>(path, {
        method: "PATCH",
        body: { ...changed, ...(confirmed.current ? { confirm_archive: true } : {}) },
        version,
      }),
    labels: LABELS,
    show: { categories: ((c: Category[]) => weightsLabel(c)) as (value: never) => string },
    onSaved: (result) => {
      confirmed.current = false;
      if (result) onSaved(result as SchemePayload);
    },
  });
  const failure =
    save.failure && save.failure !== dismissed
      ? (save.failure as { code?: string; params?: { categories?: { name: string; scores: number }[] } })
      : null;
  const archived = failure?.code === "grading_scores_archived" ? (failure.params?.categories ?? []) : [];

  return {
    save,
    run: async (values: Values) => {
      confirmed.current = false;
      last.current = values;
      await save.save(values);
    },
    /** «Финал» (оценок: 12), … when the save waits for the archive confirmation. */
    archive: archived.length ? archived.map((c) => `«${c.name}» (оценок: ${c.scores})`).join(", ") : null,
    confirm: async () => {
      if (!last.current) return;
      confirmed.current = true;
      await save.save(last.current);
    },
    dismiss: () => setDismissed(save.failure),
    error: failure && failure.code !== "grading_scores_archived" ? messageOf(failure) : null,
  };
}

export function ArchiveConfirm({
  names,
  pending,
  onConfirm,
  onClose,
}: {
  names: string;
  pending: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <ConfirmModal confirmLabel="Убрать, оценки в архив" isLoading={pending} isOpen title="Убрать категории с оценками?" onClose={onClose} onConfirm={onConfirm}>
      У {names} уже есть оценки. Они не удалятся: перестанут считаться в итоге и сохранятся в архиве. Если вернуть
      категорию с тем же названием, оценки снова будут считаться.
    </ConfirmModal>
  );
}

export function ExcelActions({
  templatePath,
  importPath,
  canImport,
  onApply,
}: {
  templatePath: string;
  importPath: string;
  canImport: boolean;
  onApply: (values: SchemeFields) => Promise<void>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [applying, setApplying] = useState(false);

  const read = async (file: File) => {
    setBusy(true);
    try {
      setPreview(await uploadCsv<Preview>(importPath, file, {}, file.name.endsWith(".csv") ? "text/csv" : XLSX));
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <>
      <ExportButton label="Скачать шаблон" path={templatePath} />
      {canImport && (
        <>
          <input
            ref={input}
            accept=".xlsx,.csv"
            aria-label="Файл шкалы оценок"
            className="hidden"
            type="file"
            onChange={(e) => {
              const file = e.target.files?.[0];

              if (file) void read(file);
            }}
          />
          <LoadingButton
            isLoading={busy}
            startContent={<Icon name="upload" size={18} />}
            variant="flat"
            onPress={() => input.current?.click()}
          >
            Загрузить
          </LoadingButton>
        </>
      )}
      {preview && (
        <AppModal
          footer={
            <>
              <Button variant="light" onPress={() => setPreview(null)}>
                Отмена
              </Button>
              <LoadingButton
                color="primary"
                isDisabled={!preview.ok}
                isLoading={applying}
                onPress={async () => {
                  setApplying(true);
                  try {
                    await onApply({
                      categories: preview.categories.map(({ name, weight, kind }) => ({ name, weight, kind })),
                      pass_score: preview.pass_score,
                      target_retention: preview.target_retention,
                      target_attendance: preview.target_attendance,
                      target_pass_rate: preview.target_pass_rate,
                    });
                    setPreview(null);
                  } finally {
                    setApplying(false);
                  }
                }}
              >
                Применить
              </LoadingButton>
            </>
          }
          guard={false}
          isOpen
          size="md"
          title="Понял так"
          onClose={() => setPreview(null)}
        >
          <div className="space-y-4 text-sm">
            {preview.categories.length > 0 && (
              <ul className="space-y-1">
                {preview.categories.map((c) => (
                  <li key={c.row} className="flex justify-between gap-3">
                    <span>
                      {c.name} <span className="text-xs text-default-500">({KIND_LABEL[c.kind]})</span>
                    </span>
                    <span className="font-semibold tabular-nums">{c.weight}</span>
                  </li>
                ))}
                <li className="flex justify-between gap-3 border-t border-divider pt-1 font-medium">
                  <span>Сумма</span>
                  <span className={clsx("tabular-nums", preview.sum !== TOTAL && "text-danger")}>
                    {preview.sum} из {TOTAL}
                  </span>
                </li>
              </ul>
            )}
            <ul className="grid grid-cols-2 gap-2">
              {TARGETS.map((t) => (
                <li key={t.key}>
                  <span className="text-default-500">{t.label}:</span>{" "}
                  {preview[t.key] ?? <span className="text-default-400">без изменений</span>}
                </li>
              ))}
            </ul>
            {preview.errors.length > 0 ? (
              <ul className="space-y-1 text-danger" role="alert">
                {preview.errors.map((e) => (
                  <li key={e.message}>{e.message}</li>
                ))}
              </ul>
            ) : (
              <p className="text-success-700 dark:text-success">Ошибок нет: можно применить.</p>
            )}
          </div>
        </AppModal>
      )}
    </>
  );
}

export function notifySaved() {
  notify("Шкала оценок сохранена");
}

export { ConflictDialog };
