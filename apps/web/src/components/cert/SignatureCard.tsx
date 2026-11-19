"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@heroui/button";

import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { Segmented } from "@/components/Segmented";
import { uploadForm } from "@/hooks/certs";
import { api } from "@/lib/api";
import { notify, notifyError } from "@/lib/toast";
import { SignaturePadModal } from "./SignaturePad";

const INKS = [
  { key: "original", label: "Как есть" },
  { key: "blue", label: "Синяя" },
  { key: "black", label: "Чёрная" },
] as const;
type Ink = (typeof INKS)[number]["key"];

const CHECKER =
  "bg-[conic-gradient(#e5e7eb_25%,#fff_0_50%,#e5e7eb_0_75%,#fff_0)] bg-[length:16px_16px] dark:bg-[conic-gradient(#2a3540_25%,#1b242d_0_50%,#2a3540_0_75%,#1b242d_0)]";

export type SignatureCardProps = {
  /** Endpoint of the image: POST uploads (?ink=), POST /preview cleans only, GET reads, DELETE removes. */
  basePath: string;
  title: string;
  help: string;
  uploadLabel: string;
  savedText: string;
  deletedText: string;
  has: boolean;
  /** Changes whenever the stored image may have changed, to bust the browser cache. */
  imageKey: string | number;
  canChange: boolean;
  /** Offers the «Нарисовать подпись» pad. */
  allowDraw?: boolean;
  testId?: string;
  hint?: string;
  onChanged: (response: unknown) => void;
};

export function SignatureCard({ basePath, title, help, uploadLabel, savedText, deletedText, has, imageKey, canChange, allowDraw = false, testId = "signature", hint, onChanged }: SignatureCardProps) {
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

    void uploadForm<Blob>(`${basePath}/preview`, file.blob, file.name, { query: { ink } })
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
  }, [file, ink, basePath]);

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
      const r = await uploadForm<unknown>(basePath, file.blob, file.name, { query: { ink } });

      onChanged(r);
      setStamp(Date.now());
      reset();
      notify(savedText);
    } catch (e) {
      notifyError(e);
      setBusy(null);
    }
  }
  async function remove() {
    setBusy("delete");
    try {
      onChanged(await api<unknown>(basePath, { method: "DELETE" }));
      notify(deletedText);
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="space-y-4 rounded-2xl bg-content1 p-4 md:p-5">
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-default-500">{help}</p>
      </div>
      <div className={`flex h-44 items-center justify-center overflow-hidden rounded-xl border border-divider ${CHECKER}`}>
        {file ? (
          preview ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img alt="Результат после очистки фона" className="max-h-full max-w-full object-contain" src={preview} />
          ) : (
            <span className="rounded bg-content1/80 px-2 py-1 text-sm text-default-600">{error ? "Не удалось обработать фото" : "Убираем фон…"}</span>
          )
        ) : has ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img alt={title} className="max-h-full max-w-full object-contain" src={`${basePath}?v=${imageKey}-${stamp}`} />
        ) : (
          <span className="rounded bg-content1/80 px-2 py-1 text-sm text-default-600">Не загружено</span>
        )}
      </div>
      {hint && <p className="text-sm text-default-500">{hint}</p>}
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
            data-testid={`${testId}-file`}
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
                {has ? "Заменить фото" : uploadLabel}
              </Button>
              {allowDraw && (
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
