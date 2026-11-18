"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { ConflictDialog } from "@/components/ConflictDialog";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { QueryState } from "@/components/QueryState";
import { Segmented } from "@/components/Segmented";
import { FormSkeleton } from "@/components/Skeletons";
import { CERT_SETTINGS_KEY, uploadForm, useCanChangeCerts, useCertSettings } from "@/hooks/certs";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import type { CertSettings } from "@/lib/cert-editor/types";
import { notify, notifyError } from "@/lib/toast";
import { SignaturePadModal } from "./SignaturePad";

export function DirectorTab() {
  const query = useCertSettings();

  return (
    <QueryState errorText="Не удалось загрузить настройки" query={query} skeleton={<FormSkeleton fields={4} />}>
      {(s) => (
        <div className="space-y-5">
          <DirectorForm key={s.version} settings={s} />
          <div className="grid gap-5 lg:grid-cols-2">
            <ImageCard kind="signature" settings={s} />
            <ImageCard kind="seal" settings={s} />
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
      <div className="grid gap-3 md:grid-cols-2">
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

const INKS = [
  { key: "original", label: "Как есть" },
  { key: "blue", label: "Синяя" },
  { key: "black", label: "Чёрная" },
] as const;
type Ink = (typeof INKS)[number]["key"];

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

function ImageCard({ kind, settings }: { kind: "signature" | "seal"; settings: CertSettings }) {
  const qc = useQueryClient();
  const canChange = useCanChangeCerts();
  const copy = COPY[kind];
  const has = !!(kind === "signature" ? settings.signature_asset_id : settings.seal_asset_id);
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<{ blob: Blob; name: string } | null>(null);
  const [ink, setInk] = useState<Ink>("original");
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState<"preview" | "save" | "delete" | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [stamp, setStamp] = useState(0);

  useEffect(() => {
    if (!file) return;
    let url: string | null = null;
    let live = true;

    void uploadForm<Blob>(`/api/v1/cert-settings/${kind}/preview`, file.blob, file.name, { query: { ink } })
      .then((b) => {
        if (!live) return;
        url = URL.createObjectURL(b);
        setPreview(url);
        setError(null);
        setBusy(null);
      })
      .catch((e) => {
        if (!live) return;
        setError(e);
        setPreview(null);
        setBusy(null);
      });

    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [file, ink, kind]);

  function pick(blob: Blob, name: string) {
    setBusy("preview");
    setError(null);
    setInk("original");
    setFile({ blob, name });
  }
  function reset() {
    setFile(null);
    setPreview(null);
    setError(null);
    setBusy(null);
  }

  async function saveIt() {
    if (!file) return;
    setBusy("save");
    try {
      const r = await uploadForm<CertSettings>(`/api/v1/cert-settings/${kind}`, file.blob, file.name, { query: { ink } });

      qc.setQueryData(CERT_SETTINGS_KEY, r);
      setStamp(Date.now());
      reset();
      notify(copy.saved);
    } catch (e) {
      notifyError(e);
      setBusy(null);
    }
  }
  async function remove() {
    setBusy("delete");
    try {
      qc.setQueryData(CERT_SETTINGS_KEY, await api<CertSettings>(`/api/v1/cert-settings/${kind}`, { method: "DELETE" }));
      notify(copy.deleted);
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(null);
    }
  }

  const checker = "bg-[conic-gradient(#e5e7eb_25%,#fff_0_50%,#e5e7eb_0_75%,#fff_0)] bg-[length:16px_16px] dark:bg-[conic-gradient(#2a3540_25%,#1b242d_0_50%,#2a3540_0_75%,#1b242d_0)]";

  return (
    <section className="space-y-4 rounded-2xl bg-content1 p-4 md:p-5">
      <div>
        <h2 className="text-lg font-semibold">{copy.title}</h2>
        <p className="text-sm text-default-500">{copy.help}</p>
      </div>
      <div className={`flex h-44 items-center justify-center overflow-hidden rounded-xl border border-divider ${checker}`}>
        {file ? (
          preview ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img alt="Результат после очистки фона" className="max-h-full max-w-full object-contain" src={preview} />
          ) : (
            <span className="rounded bg-content1/80 px-2 py-1 text-sm text-default-600">{error ? "Не удалось обработать фото" : "Убираем фон…"}</span>
          )
        ) : has ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img alt={copy.title} className="max-h-full max-w-full object-contain" src={`/api/v1/cert-settings/${kind}?v=${settings.version}-${stamp}`} />
        ) : (
          <span className="rounded bg-content1/80 px-2 py-1 text-sm text-default-600">Не загружено</span>
        )}
      </div>
      {file && (
        <>
          <Segmented label="Цвет чернил" options={INKS.map((i) => ({ key: i.key, label: i.label }))} value={ink} onChange={setInk} />
          {error != null && (
            <p className="text-sm text-danger" role="alert">
              {(error as { code?: string }).code === "cert_asset_invalid" ? "Изображение не подходит: нужен PNG или JPEG до 8 МБ с заметной подписью или печатью." : "Не удалось обработать фото. Попробуйте снять ещё раз."}
            </p>
          )}
        </>
      )}
      {canChange && (
        <div className="flex flex-wrap gap-2">
          <input
            ref={input}
            accept="image/png,image/jpeg"
            capture="environment"
            className="hidden"
            data-testid={`${kind}-file`}
            type="file"
            onChange={(e) => {
              const f = e.target.files?.[0];

              if (f) pick(f, f.name);
              e.target.value = "";
            }}
          />
          {file ? (
            <>
              <LoadingButton color="primary" isDisabled={!preview} isLoading={busy === "save"} onPress={() => void saveIt()}>
                Сохранить
              </LoadingButton>
              <Button variant="flat" onPress={() => input.current?.click()}>
                Переснять
              </Button>
              <Button variant="light" onPress={reset}>
                Отмена
              </Button>
            </>
          ) : (
            <>
              <Button color="primary" startContent={<Icon name="upload" size={18} />} variant={has ? "flat" : "solid"} onPress={() => input.current?.click()}>
                {has ? "Заменить фото" : copy.upload}
              </Button>
              {kind === "signature" && (
                <Button startContent={<Icon name="pen" size={18} />} variant="flat" onPress={() => setDrawing(true)}>
                  Нарисовать подпись
                </Button>
              )}
              {has && (
                <LoadingButton color="danger" isLoading={busy === "delete"} startContent={<Icon name="trash" size={18} />} variant="light" onPress={() => void remove()}>
                  Удалить
                </LoadingButton>
              )}
            </>
          )}
        </div>
      )}
      {drawing && (
        <SignaturePadModal
          onClose={() => setDrawing(false)}
          onDone={(png) => {
            setDrawing(false);
            pick(png, "signature.png");
          }}
        />
      )}
    </section>
  );
}
