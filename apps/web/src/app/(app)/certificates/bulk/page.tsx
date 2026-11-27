"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";

import { LoadingButton } from "@/components/LoadingButton";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, QueryState } from "@/components/QueryState";
import { SelectField } from "@/components/SelectField";
import { Bone } from "@/components/Skeletons";
import { getFile, saveBlob, uploadForm, useCanIssueCerts, useRefreshIssued } from "@/hooks/certs";
import { useBranches, useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import {
  BULK_MAX_ROWS,
  STATUS_COLOR,
  STATUS_TEXT,
  bulkFileReason,
  fileProblem,
  issueLabel,
  type BulkItem,
  type BulkPreview,
  type BulkResult,
} from "@/lib/certs-bulk";
import { formatDate } from "@/lib/format";
import { notify, notifyError } from "@/lib/toast";

type TemplateOption = { id: string; name: string; lang: string };

function Rows({ items }: { items: BulkItem[] }) {
  return (
    <>
      <div className="hidden overflow-x-auto rounded-2xl bg-content1 md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-divider text-xs text-default-500">
            <tr>
              <th className="px-4 py-3 font-medium">Строка</th>
              <th className="px-4 py-3 font-medium">ФИО</th>
              <th className="px-4 py-3 font-medium">Курс · дата</th>
              <th className="px-4 py-3 font-medium">Статус</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.row} className="border-b border-divider last:border-0">
                <td className="px-4 py-3 whitespace-nowrap">{r.row}</td>
                <td className="px-4 py-3">
                  {r.name || "—"}
                  {r.linked && <span className="ml-2 text-xs text-brand-text">студент CRM</span>}
                </td>
                <td className="px-4 py-3">
                  {[r.course, r.issued_date ? formatDate(r.issued_date) : null].filter(Boolean).join(" · ") || "—"}
                </td>
                <td className="px-4 py-3">
                  <Chip color={STATUS_COLOR[r.status]} size="sm" variant="flat">
                    {STATUS_TEXT[r.status]}
                  </Chip>
                  {(r.reason ?? r.note) && <div className="mt-1 text-xs text-default-500">{r.reason ?? r.note}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul data-rows className="space-y-3 md:hidden">
        {items.map((r) => (
          <li key={r.row} className="rounded-2xl bg-content1 p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-xs text-default-500">Строка {r.row}</div>
                <div className="break-words font-medium">{r.name || "—"}</div>
                <div className="text-sm text-default-500">{[r.course, r.issued_date ? formatDate(r.issued_date) : null].filter(Boolean).join(" · ")}</div>
              </div>
              <Chip color={STATUS_COLOR[r.status]} size="sm" variant="flat">
                {STATUS_TEXT[r.status]}
              </Chip>
            </div>
            {(r.reason ?? r.note) && <p className="mt-2 text-sm text-default-500">{r.reason ?? r.note}</p>}
          </li>
        ))}
      </ul>
    </>
  );
}

export default function BulkIssuePage() {
  const { data: me } = useMe();
  const canIssue = useCanIssueCerts();
  const { data: branches = [] } = useBranches();
  const refresh = useRefreshIssued();
  const input = useRef<HTMLInputElement>(null);
  const [template, setTemplate] = useState<string | null>(null);
  const [branch, setBranch] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [preview, setPreview] = useState<BulkPreview | null>(null);
  const [result, setResult] = useState<BulkResult | null>(null);

  const templates = useQuery({
    enabled: canIssue,
    queryKey: ["cert-bulk-templates"],
    queryFn: () => api<{ items: TemplateOption[] }>("/api/v1/certificates/bulk/templates"),
  });

  const fields = () => ({ template_id: template ?? "", ...(branch ? { branch_id: branch } : {}) });
  const send = async <T,>(tail: string) => {
    if (!file) throw new Error("no file");

    return uploadForm<T>(`/api/v1/certificates/bulk/${tail}`, file, file.name, { fields: fields() });
  };
  const onError = (e: unknown) => {
    const text = bulkFileReason(e);

    if (text) setProblem(text);
    else notifyError(e);
  };

  const check = useMutation({
    mutationFn: () => send<BulkPreview>("preview"),
    onSuccess: (d) => {
      setProblem(null);
      setPreview(d);
    },
    onError,
  });
  const issue = useMutation({
    mutationFn: () => send<BulkResult>("issue"),
    onSuccess: (d) => {
      void refresh();
      setResult(d);
      notify(`Выдано сертификатов: ${d.count}`);
    },
    onError,
  });
  const download = useMutation({
    mutationFn: async (path: string) => {
      const { blob, name } = await getFile(path);

      saveBlob(blob, name ?? "file");
    },
    onError: notifyError,
  });

  const pick = (f: File | null) => {
    setPreview(null);
    setResult(null);
    const bad = f ? fileProblem(f) : null;

    setProblem(bad);
    setFile(bad ? null : f);
  };
  const reset = () => {
    setFile(null);
    setPreview(null);
    setResult(null);
    setProblem(null);
    if (input.current) input.current.value = "";
  };

  if (!canIssue && me) {
    return <EmptyState hint="Нужно право выдавать сертификаты." title="Нет доступа" />;
  }
  const needsBranch = !!me && !me.branch;
  const ready = !!file && !!template && (!needsBranch || !!branch);
  const problemRows = preview?.items.filter((i) => i.status !== "ok") ?? [];

  return (
    <>
      <PageHeader
        actions={
          <Button as={Link} href="/certificates" variant="flat">
            К реестру
          </Button>
        }
        title="Выдача из Excel"
      />

      {result ? (
        <div className="space-y-4">
          <div className="rounded-2xl bg-content1 p-5">
            <p className="text-lg font-medium">Выдано сертификатов: {result.count}</p>
            {result.skipped.length > 0 && <p className="mt-1 text-sm text-default-500">Пропущено строк: {result.skipped.length}. Ниже сказано, почему.</p>}
            <div className="mt-4 flex flex-wrap gap-2">
              <LoadingButton color="primary" isLoading={download.isPending} onPress={() => download.mutate(`/api/v1/certificates/bulk/${result.batch_id}/zip`)}>
                Скачать ZIP с PDF
              </LoadingButton>
              <Button as={Link} href={`/certificates?batch=${result.batch_id}`} variant="flat">
                Открыть в реестре
              </Button>
              <Button variant="light" onPress={reset}>
                Загрузить другой список
              </Button>
            </div>
          </div>
          {result.skipped.length > 0 && <Rows items={result.skipped} />}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <QueryState
              bare
              empty={<EmptyState bare hint="Опубликуйте шаблон в настройках сертификатов." title="Нет шаблонов для выдачи" />}
              isEmpty={(d) => d.items.length === 0}
              query={templates}
              skeleton={<Bone className="h-14 w-full rounded-xl" />}
            >
              {(d) => (
                <SelectField
                  isRequired
                  label="Шаблон"
                  options={d.items.map((t) => ({ key: t.id, label: t.name }))}
                  value={template}
                  onChange={(v) => {
                    setTemplate(v);
                    setPreview(null);
                  }}
                />
              )}
            </QueryState>
            {needsBranch && (
              <SelectField
                isRequired
                label="Филиал"
                options={branches.map((b) => ({ key: b.id, label: b.name }))}
                value={branch}
                onChange={(v) => {
                  setBranch(v);
                  setPreview(null);
                }}
              />
            )}
          </div>

          <div className="rounded-2xl bg-content1 p-5">
            <p className="text-sm text-default-500">
              Список людей в .xlsx: ФИО обязательно; курс, дата выдачи, телефон и пол необязательны. Не больше {BULK_MAX_ROWS} строк. Если телефон совпал со студентом
              вашего филиала, сертификат привяжется к нему.
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <LoadingButton isLoading={download.isPending} variant="flat" onPress={() => download.mutate("/api/v1/certificates/bulk/template")}>
                Скачать шаблон Excel
              </LoadingButton>
              <input ref={input} accept=".xlsx" aria-label="Файл списка" className="sr-only" type="file" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
              <Button variant="flat" onPress={() => input.current?.click()}>
                {file ? "Выбрать другой файл" : "Выбрать файл"}
              </Button>
              {file && <span className="min-w-0 truncate text-sm">{file.name}</span>}
            </div>
            {problem && (
              <p className="mt-3 text-sm text-danger" role="alert">
                {problem}
              </p>
            )}
            <div className="mt-4">
              <LoadingButton color="primary" isDisabled={!ready} isLoading={check.isPending} onPress={() => check.mutate()}>
                Проверить список
              </LoadingButton>
            </div>
          </div>

          {preview && (
            <>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Chip color="success" variant="flat">
                  Готовы: {preview.counts.ok}
                </Chip>
                <Chip color="danger" variant="flat">
                  С ошибками: {preview.counts.error}
                </Chip>
                <Chip color="warning" variant="flat">
                  Повторы: {preview.counts.duplicate}
                </Chip>
                {preview.linked > 0 && <Chip variant="flat">Привязано к студентам: {preview.linked}</Chip>}
              </div>
              {problemRows.length > 0 && (
                <>
                  <p className="text-sm text-default-500">Эти строки не будут выданы. Исправьте файл и проверьте снова или выдайте остальные.</p>
                  <Rows items={problemRows} />
                </>
              )}
              {preview.counts.ok === 0 ? (
                <EmptyState hint="Исправьте файл и загрузите его снова." title="Нет строк, которые можно выдать" />
              ) : (
                <div className="sticky bottom-3">
                  <LoadingButton className="w-full sm:w-auto" color="primary" isLoading={issue.isPending} onPress={() => issue.mutate()}>
                    {issueLabel(preview.counts.ok)}
                  </LoadingButton>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
}
