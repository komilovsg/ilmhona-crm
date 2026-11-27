"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Input } from "@heroui/input";

import { ConflictDialog } from "@/components/ConflictDialog";
import { LoadingButton } from "@/components/LoadingButton";
import { QueryState } from "@/components/QueryState";
import { Segmented } from "@/components/Segmented";
import { FormSkeleton } from "@/components/Skeletons";
import { CERT_SETTINGS_KEY, useCanChangeCerts, useCertSettings } from "@/hooks/certs";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import type { CertSettings } from "@/lib/cert-editor/types";
import { notify } from "@/lib/toast";
import { SignatureCard } from "./SignatureCard";

export function DirectorTab() {
  const query = useCertSettings();

  return (
    <QueryState errorText="Не удалось загрузить настройки" query={query} skeleton={<FormSkeleton fields={4} />}>
      {(s) => (
        <div className="space-y-5">
          <DirectorForm key={s.version} settings={s} />
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <DirectorImageCard kind="signature" settings={s} />
            <DirectorImageCard kind="seal" settings={s} />
          </div>
        </div>
      )}
    </QueryState>
  );
}

type Lang = "ru" | "en" | "tg";
const LANG_OPTIONS: { key: Lang; label: string }[] = [
  { key: "ru", label: "Русский" },
  { key: "en", label: "English" },
  { key: "tg", label: "Тоҷикӣ" },
];
const SUFFIX: Record<Lang, string> = { ru: "", en: "_en", tg: "_tg" };
const KEYS = ["director_name", "director_title", "director_name_en", "director_title_en", "director_name_tg", "director_title_tg"] as const;
type Values = Pick<CertSettings, (typeof KEYS)[number]>;

const pick = (r: CertSettings): Values => ({
  director_name: r.director_name,
  director_title: r.director_title,
  director_name_en: r.director_name_en,
  director_title_en: r.director_title_en,
  director_name_tg: r.director_name_tg,
  director_title_tg: r.director_title_tg,
});

function DirectorForm({ settings }: { settings: CertSettings }) {
  const qc = useQueryClient();
  const canChange = useCanChangeCerts();
  const [lang, setLang] = useState<Lang>("ru");
  const [v, setV] = useState<Values>(pick(settings));
  const save = useVersionedSave<CertSettings, Values>({
    record: settings,
    values: v,
    toValues: pick,
    apply: setV,
    request: (changed, version) => api<CertSettings>("/api/v1/cert-settings", { method: "PATCH", body: changed, version }),
    labels: {
      director_name: "Имя директора",
      director_title: "Должность",
      director_name_en: "Имя директора (EN)",
      director_title_en: "Должность (EN)",
      director_name_tg: "Имя директора (TJ)",
      director_title_tg: "Должность (TJ)",
    },
    onSaved: (r) => {
      if (r) {
        qc.setQueryData(CERT_SETTINGS_KEY, r);
        void qc.invalidateQueries({ queryKey: ["cert-fields"] });
        notify("Данные директора сохранены");
      }
    },
  });
  const fe = useFieldErrors(save.failure, [...KEYS]);
  const dirty = KEYS.some((k) => v[k] !== settings[k]);
  const nameKey = `director_name${SUFFIX[lang]}` as (typeof KEYS)[number];
  const titleKey = `director_title${SUFFIX[lang]}` as (typeof KEYS)[number];

  return (
    <section className="space-y-4 rounded-2xl bg-content1 p-4 md:p-5">
      <div>
        <h2 className="text-lg font-semibold">Директор</h2>
        <p className="text-sm text-default-500">Имя и должность подставляются в сертификат через поля «Директор: имя» и «Директор: должность».</p>
      </div>
      <Segmented label="Язык" options={LANG_OPTIONS} value={lang} onChange={setLang} />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Input key={nameKey} isDisabled={!canChange} label="Имя директора" maxLength={120} value={v[nameKey]} {...fe.field(nameKey, (x) => setV({ ...v, [nameKey]: x }))} />
        <Input key={titleKey} isDisabled={!canChange} label="Должность" maxLength={120} value={v[titleKey]} {...fe.field(titleKey, (x) => setV({ ...v, [titleKey]: x }))} />
      </div>
      <p className="text-sm text-default-500">Используется в шаблонах на этом языке. Пусто — подставится русский вариант.</p>
      {fe.message && (
        <p className="text-sm text-danger" role="alert">
          {fe.message}
        </p>
      )}
      {canChange && (
        <LoadingButton color="primary" isDisabled={!dirty || !v.director_title.trim()} isLoading={save.pending} onPress={() => void save.save(v)}>
          Сохранить
        </LoadingButton>
      )}
      <ConflictDialog save={save} />
    </section>
  );
}

const COPY = {
  signature: {
    title: "Подпись директора",
    help: "Распишитесь ручкой на белом листе и сфотографируйте — фон уберётся автоматически.",
    upload: "Загрузить фото подписи",
    saved: "Подпись сохранена",
    deleted: "Подпись удалена",
  },
  seal: {
    title: "Печать",
    help: "Сфотографируйте оттиск печати на белом листе при хорошем свете — фон уберётся автоматически.",
    upload: "Загрузить фото печати",
    saved: "Печать сохранена",
    deleted: "Печать удалена",
  },
} as const;

function DirectorImageCard({ kind, settings }: { kind: "signature" | "seal"; settings: CertSettings }) {
  const qc = useQueryClient();
  const canChange = useCanChangeCerts();
  const copy = COPY[kind];

  return (
    <SignatureCard
      allowDraw={kind === "signature"}
      basePath={`/api/v1/cert-settings/${kind}`}
      canChange={canChange}
      deletedText={copy.deleted}
      has={!!(kind === "signature" ? settings.signature_asset_id : settings.seal_asset_id)}
      help={copy.help}
      imageKey={settings.version}
      savedText={copy.saved}
      testId={kind}
      title={copy.title}
      uploadLabel={copy.upload}
      onChanged={(r) => qc.setQueryData(CERT_SETTINGS_KEY, r as CertSettings)}
    />
  );
}
