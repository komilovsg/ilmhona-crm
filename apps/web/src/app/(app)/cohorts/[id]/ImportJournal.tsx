"use client";

import { useRef, useState, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Checkbox } from "@heroui/checkbox";
import { Chip } from "@heroui/chip";
import { Input } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { SelectField } from "@/components/SelectField";
import { useRefreshAttendance } from "@/hooks/attendance";
import { messageOf, uploadCsv } from "@/lib/api";
import { fullDate } from "@/lib/education";
import { dateStatusLabel, marksToWrite, resultText, skippedChips, type JournalPreview, type JournalResult } from "@/lib/journal-import";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";

const MAX_BYTES = 2 * 1024 * 1024;
const OCTET = "application/octet-stream";

type Settings = { sheet?: string; row?: string; col?: string; create: boolean; overwrite: boolean };

function List({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title}>
      <h3 className="mb-1.5 text-sm font-medium">{title}</h3>
      <ul className="divide-y divide-divider rounded-xl border border-divider text-sm">{children}</ul>
    </section>
  );
}

/**
 * «Импорт из Excel»: the teacher's journal (.xlsx or .csv) into this cohort's attendance. Pick the
 * file, read the preview (what is found, what will be added, what differs, what is skipped), tick
 * the options, apply. The preview writes nothing; apply sends the same file with the same settings.
 */
export function ImportJournal({ cohortId, onClose }: { cohortId: string; onClose: () => void }) {
  const refresh = useRefreshAttendance();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [settings, setSettings] = useState<Settings>({ create: true, overwrite: false });
  const [preview, setPreview] = useState<JournalPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [manual, setManual] = useState(false);
  const base = `/api/v1/cohorts/${cohortId}/attendance/import`;

  const query = (s: Settings) => ({
    sheet: s.sheet,
    row: s.row,
    col: s.col,
    create_lessons: String(s.create),
    overwrite: String(s.overwrite),
  });
  const run = useMutation({
    mutationFn: (v: { file: File; settings: Settings }) =>
      uploadCsv<JournalPreview>(`${base}/preview`, v.file, query(v.settings), OCTET),
    onSuccess: (p) => {
      setError(null);
      setPreview(p);
    },
    onError: (e) => {
      setPreview(null);
      setError(messageOf(e));
    },
  });
  const apply = useMutation({
    // the detected sheet / row / column go along, so apply reads the file exactly as the preview did
    mutationFn: () =>
      uploadCsv<JournalResult>(
        `${base}/apply`,
        file as File,
        query({
          ...settings,
          sheet: preview?.detected.sheet,
          row: String(preview?.detected.row),
          col: String(preview?.detected.col),
        }),
        OCTET,
      ),
    onSuccess: (r) => {
      void refresh();
      notify(resultText(r));
      onClose();
    },
    onError: (e) => setError(messageOf(e)),
  });

  const submit = useSubmit(() => apply.mutateAsync(), !preview);

  const again = (next: Settings, f: File | null = file) => {
    setSettings(next);
    if (f) run.mutate({ file: f, settings: next });
  };
  const pick = (f: File | undefined) => {
    if (!f) return;
    if (f.size > MAX_BYTES) {
      setError("Файл слишком большой (больше 2 МБ).");

      return;
    }
    setFile(f);
    setPreview(null);
    setManual(false);
    again({ create: settings.create, overwrite: settings.overwrite }, f);
  };

  const counts = preview?.counts;
  const writes = counts ? marksToWrite(counts, settings.overwrite) : 0;
  const lessonDates = preview?.dates.filter((d) => d.status !== "lesson" && d.status !== "future") ?? [];

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!preview || writes === 0} isLoading={apply.isPending} onPress={() => submit()}>
            {preview ? `Загрузить отметок: ${writes}` : "Загрузить"}
          </LoadingButton>
        </>
      }
      isOpen
      size="2xl"
      title="Импорт посещаемости из Excel"
      onClose={onClose}
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={input}
            accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            aria-label="Файл журнала"
            className="sr-only"
            type="file"
            onChange={(e) => {
              pick(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <LoadingButton isLoading={run.isPending} startContent={<Icon name="upload" size={18} />} variant="flat" onPress={() => input.current?.click()}>
            {file ? "Другой файл" : "Выбрать файл"}
          </LoadingButton>
          <span className="min-w-0 truncate text-sm text-default-500">
            {file ? file.name : "Журнал класса: даты уроков в строке заголовка, ФИО в колонке. Excel или CSV, до 2 МБ."}
          </span>
        </div>

        {error && (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        )}

        {preview && counts && (
          <>
            <p className="text-sm text-default-600">
              Лист «{preview.detected.sheet}», даты в строке {preview.detected.row}, ФИО в колонке {preview.detected.col}.{" "}
              <button className="text-brand-text underline" type="button" onClick={() => setManual(!manual)}>
                Это не так
              </button>
            </p>
            {manual && (
              <div className="grid gap-3 sm:grid-cols-3">
                <SelectField
                  label="Лист"
                  options={preview.file.sheets.map((s) => ({ key: s, label: s }))}
                  value={settings.sheet ?? preview.detected.sheet}
                  onChange={(sheet) => again({ ...settings, sheet: sheet ?? undefined })}
                />
                <Input
                  defaultValue={String(preview.detected.row)}
                  inputMode="numeric"
                  label="Строка с датами"
                  onBlur={(e) => again({ ...settings, row: e.target.value.trim() || undefined })}
                />
                <Input
                  defaultValue={String(preview.detected.col)}
                  label="Колонка с ФИО (номер или буква)"
                  onBlur={(e) => again({ ...settings, col: e.target.value.trim() || undefined })}
                />
              </div>
            )}

            <div className="flex flex-wrap gap-2 text-sm" role="status">
              <Chip color="success" variant="flat">
                Будет добавлено: {counts.add}
              </Chip>
              <Chip variant="flat">Уже есть: {counts.same}</Chip>
              {counts.differ > 0 && (
                <Chip color="warning" variant="flat">
                  Отличается: {counts.differ}
                </Chip>
              )}
              {counts.lessons_to_create > 0 && (
                <Chip color="primary" variant="flat">
                  Уроков добавим: {counts.lessons_to_create}
                </Chip>
              )}
              {skippedChips(counts).map((t) => (
                <Chip key={t} variant="flat">
                  {t}
                </Chip>
              ))}
            </div>

            <div className="space-y-2">
              <Checkbox isSelected={settings.create} size="sm" onValueChange={(create) => again({ ...settings, create })}>
                Добавить недостающие прошедшие уроки (время и аудитория потока)
              </Checkbox>
              <Checkbox isSelected={settings.overwrite} size="sm" onValueChange={(overwrite) => again({ ...settings, overwrite })}>
                Перезаписать отличающиеся отметки
              </Checkbox>
            </div>

            {preview.unmatched.length > 0 && (
              <List title={`Не нашли в потоке: ${preview.unmatched.length}`}>
                {preview.unmatched.map((u) => (
                  <li key={u.line} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                    <span className={u.struck ? "line-through" : undefined}>{u.name}</span>
                    <span className="text-xs text-default-500">
                      {u.struck && "вычеркнут · "}
                      {u.candidates.length > 0 ? `похожи: ${u.candidates.join(", ")}` : `отметок: ${u.marks}`}
                    </span>
                  </li>
                ))}
              </List>
            )}
            {preview.missing.length > 0 && (
              <List title={`В потоке, но нет в файле: ${preview.missing.length}`}>
                {preview.missing.map((m) => (
                  <li key={m.enrollment_id} className="flex justify-between gap-2 px-3 py-2">
                    <span>{m.student_name}</span>
                    {m.status !== "активный" && <span className="text-xs text-default-500">{m.status}</span>}
                  </li>
                ))}
              </List>
            )}
            {lessonDates.length > 0 && (
              <List title="Даты без урока">
                {lessonDates.map((d) => (
                  <li key={d.col} className="flex flex-wrap justify-between gap-2 px-3 py-2">
                    <span className="tabular-nums">{fullDate(d.date)}</span>
                    <span className="text-xs text-default-500">{dateStatusLabel(d)}</span>
                  </li>
                ))}
              </List>
            )}
            {preview.differ.length > 0 && (
              <List title={`Отличаются от текущих: ${preview.differ.length}`}>
                {preview.differ.map((d) => (
                  <li key={`${d.line}-${d.date}`} className="flex flex-wrap justify-between gap-x-3 px-3 py-2">
                    <span>
                      {d.student_name} · <span className="tabular-nums">{fullDate(d.date)}</span>
                    </span>
                    <span className="text-xs text-default-500">
                      в файле «{d.mark}», сейчас: {d.current}
                    </span>
                  </li>
                ))}
              </List>
            )}
            <p className="text-xs text-default-500">«б» — был, «н» — не был, «у» — не был по уважительной причине. Пока вы не нажмёте «Загрузить», ничего не сохраняется.</p>
          </>
        )}
      </div>
    </AppModal>
  );
}
