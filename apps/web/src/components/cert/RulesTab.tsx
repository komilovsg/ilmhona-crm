"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";

import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { QueryState } from "@/components/QueryState";
import { SelectField } from "@/components/SelectField";
import { FormSkeleton } from "@/components/Skeletons";
import { useCanChangeCerts, useCertRules, useTemplates } from "@/hooks/certs";
import { useCourses, useInstructors } from "@/hooks/education";
import { api } from "@/lib/api";
import type { TemplateRule } from "@/lib/cert-editor/types";
import { notify, notifyError } from "@/lib/toast";

type Row = { course_id: string | null; instructor_id: string | null; template_id: string | null };

export function RulesTab() {
  const query = useCertRules();

  return (
    <QueryState errorText="Не удалось загрузить правила" query={query} skeleton={<FormSkeleton fields={3} />}>
      {(d) => <Rules initial={d.rules} />}
    </QueryState>
  );
}

function Rules({ initial }: { initial: TemplateRule[] }) {
  const qc = useQueryClient();
  const canChange = useCanChangeCerts();
  const { data: courses = [] } = useCourses();
  const { data: instructors = [] } = useInstructors(null);
  const templates = useTemplates().data?.items.filter((t) => t.status !== "archived") ?? [];
  const [rows, setRows] = useState<Row[]>(initial.map(({ course_id, instructor_id, template_id }) => ({ course_id, instructor_id, template_id })));
  const start = JSON.stringify(rows);
  const complete = rows.every((r) => r.course_id && r.template_id);
  const duplicate = new Set(rows.map((r) => `${r.course_id}|${r.instructor_id}`)).size !== rows.length;
  const [saved, setSaved] = useState(start);
  const dirty = JSON.stringify(rows) !== saved;

  const save = useMutation({
    mutationFn: () => api("/api/v1/cert-template-rules", { method: "PUT", body: { rules: rows } }),
    onSuccess: () => {
      setSaved(JSON.stringify(rows));
      void qc.invalidateQueries({ queryKey: ["cert-rules"] });
      notify("Правила сохранены");
    },
    onError: notifyError,
  });
  const set = (i: number, patch: Partial<Row>) => setRows(rows.map((r, j) => (i === j ? { ...r, ...patch } : r)));

  return (
    <section className="space-y-4 rounded-2xl bg-content1 p-4 md:p-5">
      <div>
        <h2 className="text-lg font-semibold">Какой шаблон для какого курса</h2>
        <p className="text-sm text-default-500">
          Если для курса (и инструктора) есть правило, сертификат выдаётся по его шаблону. Остальным подходит шаблон по умолчанию.
        </p>
      </div>
      {rows.length === 0 && <p className="text-sm text-default-500">Правил нет: всем выдаётся шаблон по умолчанию.</p>}
      <ul className="space-y-3">
        {rows.map((r, i) => (
          <li key={i} className="grid gap-3 rounded-xl bg-content2 p-3 md:grid-cols-[1fr_1fr_1fr_auto] md:items-center">
            <SelectField isDisabled={!canChange} label="Курс" options={courses.map((c) => ({ key: c.id, label: c.name }))} value={r.course_id} onChange={(v) => set(i, { course_id: v })} />
            <SelectField allLabel="Любой инструктор" isDisabled={!canChange} label="Инструктор" options={instructors.map((c) => ({ key: c.id, label: c.full_name }))} value={r.instructor_id} onChange={(v) => set(i, { instructor_id: v })} />
            <SelectField isDisabled={!canChange} label="Шаблон" options={templates.map((t) => ({ key: t.id, label: t.name }))} value={r.template_id} onChange={(v) => set(i, { template_id: v })} />
            {canChange && (
              <Button isIconOnly aria-label="Удалить правило" variant="light" onPress={() => setRows(rows.filter((_, j) => j !== i))}>
                <Icon name="trash" size={18} />
              </Button>
            )}
          </li>
        ))}
      </ul>
      {duplicate && <p className="text-sm text-danger">Для одного курса и инструктора может быть только одно правило.</p>}
      {canChange && (
        <div className="flex flex-wrap gap-2">
          <Button startContent={<Icon name="plus" size={18} />} variant="flat" onPress={() => setRows([...rows, { course_id: null, instructor_id: null, template_id: null }])}>
            Добавить правило
          </Button>
          <LoadingButton color="primary" isDisabled={!dirty || !complete || duplicate} isLoading={save.isPending} onPress={() => save.mutate()}>
            Сохранить
          </LoadingButton>
        </div>
      )}
    </section>
  );
}
