"use client";

import { useState } from "react";
import Link from "next/link";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Checkbox } from "@heroui/checkbox";

import { AppModal } from "@/components/AppModal";
import { CertPackageModal } from "@/components/certs/CertPackageModal";
import { LoadingButton } from "@/components/LoadingButton";
import { ErrorState } from "@/components/QueryState";
import { SelectField } from "@/components/SelectField";
import { Segmented } from "@/components/Segmented";
import { Bone } from "@/components/Skeletons";
import { notReadyItems, useRefreshIssued, useTemplates } from "@/hooks/certs";
import { useMe } from "@/hooks/queries";
import { api, isApiError } from "@/lib/api";
import { issueLabel, selectable, type CertLang, type CheckResult, type IssuedCert, type NotReadyItem } from "@/lib/certs";
import { can } from "@/lib/permissions";
import { notify, notifyError } from "@/lib/toast";
import type { EnrollmentRow } from "@/lib/types";

const LANGS: { key: CertLang; label: string }[] = [
  { key: "ru", label: "RU" },
  { key: "en", label: "EN" },
];

/** «Выдать сертификаты»: pick a template and language, tick the ready students, issue, then download. */
export function IssueCertificatesModal({ cohortId, onClose }: { cohortId: string; onClose: () => void }) {
  const { data: me } = useMe();
  const refresh = useRefreshIssued();
  const [template, setTemplate] = useState<string | null>(null);
  const [lang, setLang] = useState<CertLang | null>(null);
  const [unticked, setUnticked] = useState<Set<string>>(new Set());
  const [problems, setProblems] = useState<NotReadyItem[] | null>(null);
  const [clash, setClash] = useState<string[] | null>(null);
  const [pack, setPack] = useState<{ ids: string[]; title: string; closeAfter: boolean } | null>(null);
  const seesTemplates = !!me && can(me.permissions, "cert_templates", "view");

  const templates = useTemplates();
  const check = useQuery({
    queryKey: ["cert-check", cohortId, template, lang],
    queryFn: () =>
      api<CheckResult>(`/api/v1/cohorts/${cohortId}/certificates/check`, {
        params: { template_id: template ?? undefined, lang: lang ?? undefined },
      }),
    placeholderData: keepPreviousData,
    staleTime: 0,
  });
  const enrollments = useQuery({ queryKey: ["enrollments", cohortId], queryFn: () => api<EnrollmentRow[]>(`/api/v1/cohorts/${cohortId}/enrollments`) });
  const studentOf = new Map(enrollments.data?.map((e) => [e.id, e.student_id]));

  const data = check.data;
  const ready = data ? selectable(data.items) : [];
  const picked = ready.filter((i) => !unticked.has(i.enrollment_id));
  const options = seesTemplates
    ? (templates.data?.items ?? []).filter((t) => t.status === "active" && t.latest_version_no !== null).map((t) => ({ key: t.id, label: t.name }))
    : data
      ? [{ key: data.template_id, label: data.template_name }]
      : [];
  const nameOf = (id: string) => data?.items.find((i) => i.enrollment_id === id)?.student_name ?? "";

  const issue = useMutation({
    mutationFn: () =>
      api<{ items: IssuedCert[]; count: number }>(`/api/v1/cohorts/${cohortId}/certificates/issue`, {
        method: "POST",
        body: { template_id: data!.template_id, lang: data!.lang, enrollment_ids: picked.map((i) => i.enrollment_id) },
      }),
    onSuccess: (r) => {
      void refresh();
      notify(`Выдано сертификатов: ${r.count}`);
      // the package goes in the order of the list (by name), not the API's id order
      const order = new Map(data!.items.map((i, n) => [i.enrollment_id, n]));
      const ids = [...r.items].sort((a, b) => (order.get(a.enrollment_id) ?? 0) - (order.get(b.enrollment_id) ?? 0)).map((c) => c.id);

      setPack({ ids, title: "Скачать выданные сертификаты", closeAfter: true });
    },
    onError: (e) => {
      void refresh();
      const items = notReadyItems(e);

      if (items) setProblems(items);
      else if (isApiError(e) && e.code === "cert_already_issued") setClash(((e.params?.enrollment_ids as string[]) ?? []).map(nameOf).filter(Boolean));
      else notifyError(e);
    },
  });

  const issuedIds = data?.items.filter((i) => i.certificate_id).map((i) => i.certificate_id as string) ?? [];
  const toggle = (id: string, on: boolean) => {
    const next = new Set(unticked);

    if (on) next.delete(id);
    else next.add(id);
    setUnticked(next);
    setProblems(null);
    setClash(null);
  };

  if (pack)
    return (
      <CertPackageModal
        ids={pack.ids}
        title={pack.title}
        onClose={() => {
          if (pack.closeAfter) onClose();
          else setPack(null);
        }}
      />
    );

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Закрыть
          </Button>
          {issuedIds.length > 0 && (
            <Button variant="flat" onPress={() => setPack({ ids: issuedIds, title: "Скачать выданные снова", closeAfter: false })}>
              Скачать снова ({issuedIds.length})
            </Button>
          )}
          <LoadingButton color="primary" isDisabled={picked.length === 0} isLoading={issue.isPending} onPress={() => issue.mutate()}>
            {issueLabel(picked.length)}
          </LoadingButton>
        </>
      }
      isOpen
      size="2xl"
      title="Выдать сертификаты"
      onClose={onClose}
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <SelectField
            label="Шаблон"
            options={options}
            value={template ?? data?.template_id ?? null}
            onChange={(v) => {
              setTemplate(v);
              setUnticked(new Set());
            }}
          />
          <Segmented
            label="Язык сертификата"
            options={data?.lang === "tg" ? [...LANGS, { key: "tg" as const, label: "TJ" }] : LANGS}
            value={lang ?? data?.lang ?? "ru"}
            onChange={setLang}
          />
        </div>

        {check.isError && !data && <ErrorState bare onRetry={() => void check.refetch()} retrying={check.isFetching} text="Не удалось проверить студентов" />}
        {check.isPending && (
          <div className="space-y-2">
            {Array.from({ length: 5 }, (_, i) => (
              <Bone key={i} className="h-12 w-full rounded-xl" />
            ))}
          </div>
        )}
        {data && data.items.length === 0 && <p className="text-center text-default-500">В потоке нет студентов.</p>}
        {data && data.items.length > 0 && (
          <ul aria-busy={check.isFetching} className="divide-y divide-divider rounded-xl border border-divider">
            {data.items.map((i) => {
              const studentId = studentOf.get(i.enrollment_id);

              return (
                <li key={i.enrollment_id} className="flex items-start gap-3 px-3 py-2.5">
                  <Checkbox
                    aria-label={`Выбрать: ${i.student_name}`}
                    isDisabled={i.status !== "ready"}
                    isSelected={i.status === "ready" && !unticked.has(i.enrollment_id)}
                    onValueChange={(on) => toggle(i.enrollment_id, on)}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-x-3">
                      <span className="font-medium">{i.student_name}</span>
                      <span className="text-sm tabular-nums text-default-500">{i.score !== null ? `${i.score} б.` : ""}</span>
                    </div>
                    {i.status === "ready" && <span className="text-sm text-success">Готово</span>}
                    {i.status === "issued" && <span className="text-sm text-default-500">Уже выдан №{i.number}</span>}
                    {i.status === "fix" && (
                      <div className="text-sm">
                        <span className="font-medium text-danger">Нужно исправить</span>
                        <span className="text-default-600">: {i.text}</span>
                        {studentId && (
                          <>
                            {" "}
                            <Link className="text-brand-text" href={`/students/${studentId}`} target="_blank">
                              Открыть карточку
                            </Link>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {data && (
          <p className="text-sm text-default-500">
            Готово: {data.counts.ready} · уже выдано: {data.counts.issued} · нужно исправить: {data.counts.fix}
          </p>
        )}
        {problems && (
          <div className="space-y-1 rounded-xl bg-danger/10 p-3 text-sm" role="alert">
            <p className="font-medium text-danger">Выдача не выполнена: сертификаты не выданы никому.</p>
            <ul className="list-disc pl-5">
              {problems.map((p) => (
                <li key={p.enrollment_id}>
                  {p.student_name}: {p.text}
                </li>
              ))}
            </ul>
          </div>
        )}
        {clash && (
          <p className="rounded-xl bg-warning/10 p-3 text-sm" role="alert">
            Сертификат уже выдан{clash.length ? `: ${clash.join(", ")}` : ""}. Список обновлён, выберите остальных.
          </p>
        )}
      </div>
    </AppModal>
  );
}
