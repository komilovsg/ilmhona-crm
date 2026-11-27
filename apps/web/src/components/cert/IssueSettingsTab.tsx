"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Input } from "@heroui/input";
import { Switch } from "@heroui/switch";

import { ConflictDialog } from "@/components/ConflictDialog";
import { LoadingButton } from "@/components/LoadingButton";
import { QueryState } from "@/components/QueryState";
import { FormSkeleton } from "@/components/Skeletons";
import { CERT_SETTINGS_KEY, useCertSettings } from "@/hooks/certs";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import type { CertSettings } from "@/lib/cert-editor/types";
import { notify } from "@/lib/toast";

type Values = { verify_base_url: string; allow_non_graduate: boolean };

const pick = (r: CertSettings): Values => ({ verify_base_url: r.verify_base_url ?? "", allow_non_graduate: r.allow_non_graduate });

/** «Выдача»: the two settings only the superadmin sees and changes. */
export function IssueSettingsTab() {
  const query = useCertSettings();

  return (
    <QueryState errorText="Не удалось загрузить настройки" query={query} skeleton={<FormSkeleton fields={2} />}>
      {(s) => <IssueSettingsForm key={s.version} settings={s} />}
    </QueryState>
  );
}

function IssueSettingsForm({ settings }: { settings: CertSettings }) {
  const qc = useQueryClient();
  const [v, setV] = useState<Values>(pick(settings));
  const save = useVersionedSave<CertSettings, Values>({
    record: settings,
    values: v,
    toValues: pick,
    apply: setV,
    request: (changed, version) => api<CertSettings>("/api/v1/cert-settings", { method: "PATCH", body: changed, version }),
    labels: { verify_base_url: "Адрес проверки QR", allow_non_graduate: "Выдача не выпускникам" },
    show: { allow_non_graduate: (x: boolean) => (x ? "разрешена" : "запрещена") },
    onSaved: (r) => {
      if (r) {
        qc.setQueryData(CERT_SETTINGS_KEY, r);
        notify("Настройки выдачи сохранены");
      }
    },
  });
  const fe = useFieldErrors(save.failure, ["verify_base_url", "allow_non_graduate"]);
  const dirty = v.verify_base_url !== (settings.verify_base_url ?? "") || v.allow_non_graduate !== settings.allow_non_graduate;

  return (
    <section className="space-y-5 rounded-2xl bg-content1 p-4 md:p-5">
      <div>
        <h2 className="text-lg font-semibold">Выдача и проверка</h2>
        <p className="text-sm text-default-500">Эти настройки видны и меняются только суперадмином.</p>
      </div>
      <Input
        description="Например https://check.ilmhona.org. Меняйте только до печати: старые QR ведут на прежний адрес"
        label="Адрес проверки QR"
        maxLength={200}
        placeholder="https://"
        type="url"
        value={v.verify_base_url}
        {...fe.field("verify_base_url", (x) => setV({ ...v, verify_base_url: x }))}
      />
      <Switch isSelected={v.allow_non_graduate} onValueChange={(x) => setV({ ...v, allow_non_graduate: x })}>
        <span className="block font-medium">Разрешить выдачу не выпускникам</span>
        <span className="block text-sm text-default-500">Комментарий при выдаче обязателен, запись попадает в журнал.</span>
      </Switch>
      {fe.message && (
        <p className="text-sm text-danger" role="alert">
          {fe.message}
        </p>
      )}
      <LoadingButton color="primary" isDisabled={!dirty} isLoading={save.pending} onPress={() => void save.save(v)}>
        Сохранить
      </LoadingButton>
      <ConflictDialog save={save} />
    </section>
  );
}
