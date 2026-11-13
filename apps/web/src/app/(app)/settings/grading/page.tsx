"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ArchiveConfirm,
  ConflictDialog,
  ExcelActions,
  SchemeChips,
  SchemeEditor,
  SchemeTargets,
  notifySaved,
  useSchemeSave,
  type SchemePayload,
} from "@/components/GradingScheme";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { PageHeader } from "@/components/PageHeader";
import { QueryState } from "@/components/QueryState";
import { SchemeSkeleton } from "@/components/Skeletons";
import { api } from "@/lib/api";
import { fullDate } from "@/lib/education";

type Standard = SchemePayload & {
  updated_at: string;
  updated_by_name: string | null;
  cohorts_with_own: number;
};

const PATH = "/api/v1/grading/standard";

export default function GradingStandardPage() {
  const query = useQuery({ queryKey: ["grading", "standard"], queryFn: () => api<Standard>(PATH) });

  return (
    <>
      <p className="mb-1 text-sm text-default-500">Настройки</p>
      <PageHeader title="Стандарты академии" />
      <QueryState errorText="Не удалось загрузить стандарт оценок" query={query} skeleton={<SchemeSkeleton />}>
        {(data) => <Standard key={data.version} data={data} />}
      </QueryState>
    </>
  );
}

function Standard({ data }: { data: Standard }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const saved = (result: SchemePayload) => {
    queryClient.setQueryData(["grading", "standard"], result);
    void queryClient.invalidateQueries({ queryKey: ["grading"] });
    void queryClient.invalidateQueries({ queryKey: ["grades"] });
    setEditing(false);
    notifySaved();
  };
  const s = useSchemeSave(PATH, data, saved);

  return (
    <div className="space-y-5">
      <section className="space-y-4 rounded-2xl bg-content1 p-4 md:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Шкала оценок</h2>
            <p className="text-sm text-default-500">
              Итог студента = сумма баллов по категориям (всего 100). Действует для всех потоков, у которых нет своей
              шкалы{data.cohorts_with_own ? ` (своя шкала у потоков: ${data.cohorts_with_own})` : ""}.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ExcelActions
              canImport={data.can_edit}
              importPath={`${PATH}/import`}
              templatePath={`${PATH}/template`}
              onApply={(values) => s.run(values)}
            />
            {data.can_edit && !editing && (
              <LoadingButton color="primary" startContent={<Icon name="edit" size={18} />} onPress={() => setEditing(true)}>
                Изменить
              </LoadingButton>
            )}
          </div>
        </div>
        {editing ? (
          <SchemeEditor
            initial={data.scheme}
            saving={s.save.pending}
            onCancel={() => setEditing(false)}
            onSave={(draft) => void s.run(draft)}
          />
        ) : (
          <>
            <SchemeChips scheme={data.scheme} />
            <SchemeTargets scheme={data.scheme} />
          </>
        )}
        {s.error && (
          <p className="text-sm text-danger" role="alert">
            {s.error}
          </p>
        )}
        <p className="text-xs text-default-500">
          Изменено {fullDate(data.updated_at.slice(0, 10))}
          {data.updated_by_name ? ` · ${data.updated_by_name}` : ""}.
          {!data.can_edit && " Менять стандарт может только суперадмин."}
        </p>
      </section>
      <ConflictDialog save={s.save} />
      {s.archive && (
        <ArchiveConfirm names={s.archive} pending={s.save.pending} onClose={s.dismiss} onConfirm={() => void s.confirm()} />
      )}
    </div>
  );
}
