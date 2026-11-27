"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { Input } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { EmptyState, QueryState } from "@/components/QueryState";
import { RowMenu } from "@/components/RowMenu";
import { SelectField } from "@/components/SelectField";
import { CardGridSkeleton } from "@/components/Skeletons";
import { CERT_TEMPLATES_KEY, useCanChangeCerts, useTemplates } from "@/hooks/certs";
import { api } from "@/lib/api";
import type { TemplateDetail, TemplateListItem } from "@/lib/cert-editor/types";
import { notify, notifyError } from "@/lib/toast";

export const LANGS = [
  { key: "ru", label: "Русский" },
  { key: "en", label: "English" },
  { key: "tg", label: "Тоҷикӣ" },
];
const langLabel = (k: string) => LANGS.find((l) => l.key === k)?.label ?? k;
const changedOn = new Intl.DateTimeFormat("ru-RU", { timeZone: "Asia/Dushanbe" });

export function statusLine(t: TemplateListItem): string {
  if (t.status === "archived") return "В архиве";
  if (!t.latest_version_no) return "Черновик · не опубликовано";

  return `v${t.latest_version_no}${t.has_unpublished_changes ? " · есть неопубликованные изменения" : " · опубликовано"}`;
}

export function TemplatesTab() {
  const query = useTemplates();
  const canChange = useCanChangeCerts();
  const router = useRouter();
  const qc = useQueryClient();
  const [creating, setCreating] = useState<{ from: string | null } | null>(null);

  const archive = useMutation({
    mutationFn: (t: TemplateListItem) =>
      api(`/api/v1/cert-templates/${t.id}`, {
        method: "PATCH",
        version: t.version,
        body: { status: t.status === "archived" ? "active" : "archived" },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CERT_TEMPLATES_KEY });
      notify("Готово");
    },
    onError: notifyError,
  });

  const actions = (t: TemplateListItem) => [
    { key: "open", label: canChange ? "Открыть конструктор" : "Посмотреть", icon: "edit" },
    ...(canChange
      ? [
          { key: "copy", label: "Дублировать", icon: "copy" },
          t.status === "archived" ? { key: "archive", label: "Вернуть из архива", icon: "upload" } : { key: "archive", label: "В архив", icon: "archive" },
        ]
      : []),
  ];
  const onAction = (t: TemplateListItem, key: string) => {
    if (key === "open") router.push(`/settings/certificates/${t.id}`);
    else if (key === "copy") setCreating({ from: t.id });
    else archive.mutate(t);
  };

  return (
    <>
      {canChange && (
        <div className="mb-4 flex justify-end">
          <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setCreating({ from: null })}>
            Новый шаблон
          </Button>
        </div>
      )}
      <QueryState
        empty={<EmptyState hint="Создайте первый шаблон или импортируйте готовые." title="Шаблонов пока нет" />}
        errorText="Не удалось загрузить шаблоны"
        isEmpty={(d) => d.items.length === 0}
        query={query}
        skeleton={<CardGridSkeleton cards={4} lines={3} />}
      >
        {(d) => (
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {d.items.map((t) => (
              <li key={t.id} className="flex flex-col gap-2 rounded-2xl bg-content1 p-4">
                <div className="flex items-start justify-between gap-2">
                  <Link className="min-w-0 font-medium hover:text-brand-text" href={`/settings/certificates/${t.id}`}>
                    <span className="block truncate">{t.name}</span>
                  </Link>
                  <RowMenu actions={actions(t)} label={`Действия: ${t.name}`} onAction={(k) => onAction(t, k)} />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Chip size="sm" variant="flat">
                    {langLabel(t.lang)}
                  </Chip>
                  <Chip color={t.status === "archived" ? "default" : t.latest_version_no ? "success" : "warning"} size="sm" variant="flat">
                    {t.status === "archived" ? "Архив" : t.latest_version_no ? "Опубликован" : "Черновик"}
                  </Chip>
                </div>
                <p className="text-sm text-default-600">{statusLine(t)}</p>
                <p className="text-xs text-default-500">Изменён {changedOn.format(new Date(t.updated_at))}</p>
              </li>
            ))}
          </ul>
        )}
      </QueryState>
      {creating && <NewTemplateModal from={creating.from} items={query.data?.items ?? []} onClose={() => setCreating(null)} />}
    </>
  );
}

function NewTemplateModal({ from, items, onClose }: { from: string | null; items: TemplateListItem[]; onClose: () => void }) {
  const router = useRouter();
  const source = items.find((t) => t.id === from);
  const [name, setName] = useState(source ? `${source.name} (копия)` : "");
  const [lang, setLang] = useState(source?.lang ?? "ru");
  const [fromId, setFromId] = useState<string | null>(from);
  const create = useMutation({
    mutationFn: () =>
      api<TemplateDetail>("/api/v1/cert-templates", { method: "POST", body: { name: name.trim(), lang, ...(fromId ? { from_template_id: fromId } : {}) } }),
    onSuccess: (t) => router.push(`/settings/certificates/${t.id}`),
    onError: notifyError,
  });

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!name.trim()} isLoading={create.isPending} onPress={() => create.mutate()}>
            Создать
          </LoadingButton>
        </>
      }
      isOpen
      size="md"
      title={source ? "Дублировать шаблон" : "Новый шаблон"}
      onClose={onClose}
    >
      <div className="space-y-4">
        <Input isRequired label="Название" value={name} onValueChange={setName} />
        <SelectField label="Язык" options={LANGS} value={lang} onChange={(v) => setLang(v ?? "ru")} />
        <SelectField allLabel="Пустой лист" label="Начать с шаблона" options={items.map((t) => ({ key: t.id, label: t.name }))} value={fromId} onChange={setFromId} />
      </div>
    </AppModal>
  );
}
