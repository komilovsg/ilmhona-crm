"use client";

import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";

import { AppModal } from "@/components/AppModal";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { SelectField } from "@/components/SelectField";
import { useCourses } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { useRefreshSales } from "@/hooks/sales";
import { messageOf, uploadCsv } from "@/lib/api";
import { LEAD_SOURCES } from "@/lib/sales";
import type { ImportPreview } from "@/lib/sales-types";
import { notify } from "@/lib/toast";

const PREVIEW = "/api/v1/leads/import/preview";
const CONFIRM = "/api/v1/leads/import";
const FIELD_LABELS: Record<string, string> = {
  full_name: "ФИО",
  first_name: "Имя",
  last_name: "Фамилия",
  phone: "Телефон",
  source: "Источник",
  course: "Курс",
  comment: "Комментарий",
};
const NONE = "— нет —";
const MAX_BYTES = 2 * 1024 * 1024;

type Done = { created: number; skipped: number; needs_review: number; duplicates: number };

/**
 * CSV import in three steps: pick the file, check the preview (column mapping, cleaned names,
 * «проверить» flags, known phones), confirm. The preview writes nothing: the file is sent again
 * with the same settings only when the user confirms.
 */
export function ImportWizard({ onClose }: { onClose: () => void }) {
  const refresh = useRefreshSales();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const { data: courses = [] } = useCourses();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null> | null>(null);
  const [branchId, setBranchId] = useState<string | null>(me?.branch?.id ?? null);
  const [source, setSource] = useState("Facebook");
  const [courseId, setCourseId] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [done, setDone] = useState<Done | null>(null);
  const [error, setError] = useState<string | null>(null);

  const params = (m: Record<string, string | null> | null, s = source, c = courseId, b = branchId) => ({
    mapping: m ? JSON.stringify(m) : undefined,
    source: s,
    course_id: c ?? undefined,
    branch_id: b ?? undefined,
  });

  const run = useMutation({
    mutationFn: (v: { file: File; mapping: Record<string, string | null> | null; source?: string; course?: string | null; branch?: string | null }) =>
      uploadCsv<ImportPreview>(PREVIEW, v.file, params(v.mapping, v.source ?? source, v.course === undefined ? courseId : v.course, v.branch === undefined ? branchId : v.branch)),
    onSuccess: (p) => {
      setError(null);
      setPreview(p);
      setMapping(p.mapping);
    },
    onError: (e) => {
      setPreview(null);
      setError(messageOf(e));
    },
  });
  const confirm = useMutation({
    mutationFn: () => uploadCsv<Done>(CONFIRM, file as File, params(mapping)),
    onSuccess: (d) => {
      void refresh();
      setDone(d);
      notify(`Импортировано лидов: ${d.created}`);
    },
    onError: (e) => setError(messageOf(e)),
  });

  const pick = (f: File | undefined) => {
    if (!f) return;
    if (f.size > MAX_BYTES) {
      setError("Файл слишком большой (больше 2 МБ).");

      return;
    }
    setFile(f);
    setPreview(null);
    if (!branchId) {
      setError("Выберите филиал: после этого покажем, что будет импортировано.");

      return;
    }
    run.mutate({ file: f, mapping: null });
  };
  const ready = preview && preview.totals.importable > 0 && !!branchId;

  if (done)
    return (
      <AppModal
        footer={
          <Button color="primary" onPress={onClose}>
            Готово
          </Button>
        }
        isOpen
        size="md"
        title="Импорт завершён"
        onClose={onClose}
      >
        <ul className="space-y-1 text-sm">
          <li>
            Добавлено лидов: <b>{done.created}</b>
          </li>
          <li>Пропущено пустых строк: {done.skipped}</li>
          <li>Нужна проверка имени: {done.needs_review}</li>
          <li>С телефоном, который уже есть: {done.duplicates}</li>
        </ul>
      </AppModal>
    );

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!ready} isLoading={confirm.isPending} onPress={() => confirm.mutate()}>
            {preview ? `Импортировать ${preview.totals.importable}` : "Импортировать"}
          </LoadingButton>
        </>
      }
      isOpen
      size="2xl"
      title="Импорт лидов из CSV"
      onClose={onClose}
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={input}
            accept=".csv,text/csv,text/plain"
            aria-label="Файл CSV"
            className="sr-only"
            type="file"
            onChange={(e) => {
              pick(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <LoadingButton
            isLoading={run.isPending}
            startContent={<Icon name="upload" size={18} />}
            variant="flat"
            onPress={() => input.current?.click()}
          >
            {file ? "Другой файл" : "Выбрать файл CSV"}
          </LoadingButton>
          <span className="min-w-0 truncate text-sm text-default-500">
            {file ? file.name : "Выгрузка формы Facebook или любая таблица с заголовками. До 2 МБ и 2000 строк."}
          </span>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <SelectField
            isDisabled={!!me?.branch}
            isRequired
            label="Филиал"
            options={branches.map((b) => ({ key: b.id, label: b.name }))}
            value={branchId}
            onChange={(b) => {
              setBranchId(b);
              if (file) run.mutate({ file, mapping, branch: b });
            }}
          />
          <SelectField
            label="Источник по умолчанию"
            options={LEAD_SOURCES.map((s) => ({ key: s, label: s }))}
            value={source}
            onChange={(s) => {
              setSource(s ?? "Facebook");
              if (file) run.mutate({ file, mapping, source: s ?? "Facebook" });
            }}
          />
          <SelectField
            allLabel="Курс не задан"
            label="Курс по умолчанию"
            options={courses.map((c) => ({ key: c.id, label: c.name }))}
            value={courseId}
            onChange={(c) => {
              setCourseId(c);
              if (file) run.mutate({ file, mapping, course: c });
            }}
          />
        </div>

        {error && (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        )}

        {preview && mapping && (
          <>
            <section aria-label="Колонки">
              <h3 className="mb-2 text-sm font-medium">Колонки файла</h3>
              <div className="grid gap-3 sm:grid-cols-3">
                {Object.keys(FIELD_LABELS).map((field) => (
                  <SelectField
                    key={field}
                    allLabel={NONE}
                    label={FIELD_LABELS[field]}
                    options={preview.headers.map((h) => ({ key: h, label: h }))}
                    value={mapping[field] ?? null}
                    onChange={(h) => {
                      const next = { ...mapping, [field]: h };

                      setMapping(next);
                      if (file) run.mutate({ file, mapping: next });
                    }}
                  />
                ))}
              </div>
            </section>

            <div className="flex flex-wrap gap-2 text-sm" role="status">
              <Chip variant="flat">Строк: {preview.totals.rows}</Chip>
              <Chip color="success" variant="flat">
                Будет добавлено: {preview.totals.importable}
              </Chip>
              {preview.totals.skipped > 0 && <Chip variant="flat">Пустых: {preview.totals.skipped}</Chip>}
              {preview.totals.needs_review > 0 && (
                <Chip color="warning" variant="flat">
                  Проверить имя: {preview.totals.needs_review}
                </Chip>
              )}
              {preview.totals.duplicates > 0 && (
                <Chip color="secondary" variant="flat">
                  Телефон уже есть: {preview.totals.duplicates}
                </Chip>
              )}
            </div>

            {preview.rows.length > 0 && (
              <div className="overflow-x-auto rounded-xl border border-divider">
                <table className="w-full min-w-[34rem] text-left text-sm">
                  <thead className="border-b border-divider text-xs text-default-500">
                    <tr>
                      <th className="px-3 py-2 font-medium">Стр.</th>
                      <th className="px-3 py-2 font-medium">ФИО</th>
                      <th className="px-3 py-2 font-medium">Телефон</th>
                      <th className="px-3 py-2 font-medium">Источник</th>
                      <th className="px-3 py-2 font-medium">Примечание</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((r) => (
                      <tr key={r.line} className="border-b border-divider last:border-0">
                        <td className="px-3 py-2 text-default-500">{r.line}</td>
                        <td className="px-3 py-2">
                          {r.skip ? "—" : r.full_name}
                          {r.raw_name && r.raw_name !== r.full_name && (
                            <div className="text-xs text-default-500">было: {r.raw_name}</div>
                          )}
                        </td>
                        <td className="px-3 py-2">{r.phone ?? "—"}</td>
                        <td className="px-3 py-2">{r.source}</td>
                        <td className="px-3 py-2">
                          <div className="flex flex-wrap gap-1">
                            {r.skip && (
                              <Chip size="sm" variant="flat">
                                пустая строка
                              </Chip>
                            )}
                            {r.needs_review && (
                              <Chip color="warning" size="sm" variant="flat">
                                проверить имя
                              </Chip>
                            )}
                            {r.duplicates.length > 0 && (
                              <Chip color="secondary" size="sm" variant="flat">
                                {r.duplicates[0].kind === "file"
                                  ? `дубль строки ${r.duplicates[0].line}`
                                  : `уже есть: ${r.duplicates[0].full_name}`}
                              </Chip>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {preview.truncated && (
              <p className="text-xs text-default-500">Показаны первые строки. Импортируются все.</p>
            )}
            <p className="text-xs text-default-500">Пока вы не нажмёте «Импортировать», ничего не сохраняется.</p>
          </>
        )}
      </div>
    </AppModal>
  );
}
