"use client";

import { useState } from "react";
import { Input } from "@heroui/input";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ConflictDialog } from "@/components/ConflictDialog";
import { LoadingButton } from "@/components/LoadingButton";
import { QueryState } from "@/components/QueryState";
import { FormSkeleton } from "@/components/Skeletons";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import { notify } from "@/lib/toast";

type AcademySettings = {
  stale_days: number;
  warn_days: number;
  can_edit: boolean;
  version: number;
  updated_at: string;
  updated_by_name: string | null;
};
type Values = { stale_days: string };

const KEY = ["academy-settings"];
const PATH = "/api/v1/academy-settings";

export function StaleSettings() {
  const query = useQuery({ queryKey: KEY, queryFn: () => api<AcademySettings>(PATH) });

  return (
    <QueryState errorText="Не удалось загрузить настройки" query={query} skeleton={<FormSkeleton fields={1} />}>
      {(s) => <StaleForm key={s.version} settings={s} />}
    </QueryState>
  );
}

const pick = (r: AcademySettings): Values => ({ stale_days: String(r.stale_days) });

function StaleForm({ settings }: { settings: AcademySettings }) {
  const qc = useQueryClient();
  const [v, setV] = useState<Values>(pick(settings));
  const days = Number(v.stale_days);
  const valid = Number.isInteger(days) && days >= 20 && days <= 730;
  const save = useVersionedSave<AcademySettings, Values>({
    record: settings,
    values: v,
    toValues: pick,
    apply: setV,
    request: (_, version) => api<AcademySettings>(PATH, { method: "PATCH", body: { stale_days: days }, version }),
    labels: { stale_days: "Дней без отметок" },
    onSaved: (r) => {
      if (r) {
        qc.setQueryData(KEY, r);
        void qc.invalidateQueries({ queryKey: ["cohorts"] });
        notify("Настройка сохранена");
      }
    },
  });
  const fe = useFieldErrors(save.failure, ["stale_days"]);

  return (
    <section className="space-y-4 rounded-2xl bg-content1 p-4 md:p-5">
      <div>
        <h2 className="text-lg font-semibold">Автозакрытие потоков</h2>
        <p className="text-sm text-default-500">
          Активный поток, в котором нет отметок посещаемости столько дней, закрывается сам: студенты получают итог по
          проходному баллу, будущие уроки без отметок отменяются и освобождают аудиторию. Если отметок не было совсем,
          дни считаются от даты старта. За {settings.warn_days} дней до закрытия поток помечается предупреждением.
        </p>
      </div>
      <Input
        className="max-w-xs"
        description="От 20 до 730 дней"
        inputMode="numeric"
        isDisabled={!settings.can_edit}
        label="Дней без отметок"
        value={v.stale_days}
        {...fe.field("stale_days", (x) => setV({ stale_days: x.replace(/\D/g, "") }))}
      />
      {fe.message && (
        <p className="text-sm text-danger" role="alert">
          {fe.message}
        </p>
      )}
      {settings.can_edit ? (
        <LoadingButton
          color="primary"
          isDisabled={!valid || v.stale_days === String(settings.stale_days)}
          isLoading={save.pending}
          onPress={() => void save.save(v)}
        >
          Сохранить
        </LoadingButton>
      ) : (
        <p className="text-xs text-default-500">Менять настройку может только суперадмин.</p>
      )}
      <ConflictDialog save={save} />
    </section>
  );
}
