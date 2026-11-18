"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@heroui/button";
import { Switch } from "@heroui/switch";

import { ConfirmModal } from "@/components/ConfirmModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { Segmented } from "@/components/Segmented";
import { postForPdf, saveBlob, uploadForm, useCanChangeCerts, useCertCatalog, useCertSettings } from "@/hooks/certs";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api, isApiError, messageOf } from "@/lib/api";
import { makeBlock, sampleLayout, type BlockKey } from "@/lib/cert-editor/blocks";
import { fontFaceCss } from "@/lib/cert-editor/fonts";
import { fitScale, nudgeDelta, PX_PER_MM } from "@/lib/cert-editor/geometry";
import { initialState, isDirty, reducer } from "@/lib/cert-editor/reducer";
import type { CertAsset, Layer, Layout, Run, SampleKind, TemplateDetail } from "@/lib/cert-editor/types";
import { useMediaQuery } from "@/lib/client-store";
import { notify, notifyError } from "@/lib/toast";
import { Canvas } from "./Canvas";
import { LeftPanel } from "./LeftPanel";
import { RightPanel } from "./RightPanel";
import { Toolbar } from "./Toolbar";
import type { EditorApi, View } from "./view";

type Values = { name: string; lang: string; draft: Layout };

const SAMPLES: { key: SampleKind; label: string }[] = [
  { key: "short", label: "Короткое имя" },
  { key: "long", label: "Длинное имя" },
  { key: "female", label: "Женское имя" },
];

type Problem = { loc: string[]; msg: string };

function isEditable(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;

  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

export function Constructor({ initial, onReplace }: { initial: TemplateDetail; onReplace: (d: TemplateDetail) => void }) {
  const router = useRouter();
  const wide = useMediaQuery("(min-width: 1280px)");
  const canEdit = useCanChangeCerts();
  const catalog = useCertCatalog().data;
  const settings = useCertSettings().data;
  const [state, dispatch] = useReducer(reducer, initial.draft, initialState);
  const [detail, setDetail] = useState(initial);
  const [name, setName] = useState(initial.name);
  const [lang, setLang] = useState(initial.lang);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showSample, setShowSample] = useState(false);
  const [sample, setSample] = useState<SampleKind>("short");
  const [zoom, setZoom] = useState<number | null>(null);
  const [avail, setAvail] = useState(900);
  const [busy, setBusy] = useState<null | "check" | "publish" | "upload" | "restore">(null);
  const [confirm, setConfirm] = useState<null | "back" | "publish" | { restore: number }>(null);
  const editorApi = useRef<EditorApi | null>(null);
  const stage = useRef<HTMLDivElement>(null);
  const latest = useRef(state);
  const sent = useRef<Layout | null>(null);
  const [sentIds, setSentIds] = useState<string[]>([]);
  const imageTarget = useRef<{ replace: string | null; spot: { x: number; y: number } } | null>(null);
  const imageInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    latest.current = state;
  });

  const labelOf = useCallback((key: string) => catalog?.fields.find((f) => f.key === key)?.label ?? key, [catalog]);
  const dirty = isDirty(state) || name !== detail.name || lang !== detail.lang;

  const save = useVersionedSave<TemplateDetail, Values>({
    record: initial,
    values: { name, lang, draft: state.layout },
    toValues: (r) => ({ name: r.name, lang: r.lang, draft: r.draft }),
    apply: (v) => {
      setName(v.name);
      setLang(v.lang);
      dispatch({ type: "set_layout", layout: v.draft });
    },
    request: (changed, version, all) => {
      sent.current = all.draft;
      setSentIds(all.draft.layers.map((l) => l.id));

      return api<TemplateDetail>(`/api/v1/cert-templates/${initial.id}`, { method: "PATCH", body: changed, version });
    },
    labels: { name: "Название", lang: "Язык", draft: "Макет" },
    show: { draft: () => "макет изменён" },
    onSaved: (r) => {
      const d = r as TemplateDetail | null;

      if (!d) return;
      setDetail(d);
      setName(d.name);
      setLang(d.lang);
      const same = JSON.stringify(latest.current.layout) === JSON.stringify(sent.current);

      dispatch(same ? { type: "adopt", layout: d.draft } : { type: "saved", layout: sent.current ?? undefined });
      notify("Шаблон сохранён");
    },
  });

  const failure = save.failure;
  const problems: { text: string; id?: string }[] = useMemo(() => {
    if (!isApiError(failure)) return [];
    const list = (failure.params?.problems as Problem[] | undefined) ?? [];

    if (failure.code === "cert_field_unknown")
      return [{ text: `Неизвестное поле «${String(failure.params?.field)}»`, id: String(failure.params?.layer ?? "") || undefined }];

    return list.map((p) => {
      const i = p.loc.indexOf("layers");
      const id = i >= 0 ? sentIds[Number(p.loc[i + 1])] : undefined;

      return { text: `${id ? `Блок «${id}»: ` : ""}${p.msg} (${p.loc.join(" / ")})`, id };
    });
  }, [failure, sentIds]);

  // ---- sizing
  useEffect(() => {
    const el = stage.current;

    if (!el) return;
    const ro = new ResizeObserver(() => setAvail(el.clientWidth));

    ro.observe(el);
    setAvail(el.clientWidth);

    return () => ro.disconnect();
  }, [wide]);
  const fitMode = zoom === null;
  const scale = fitMode ? fitScale(state.layout.page, Math.max(300, avail - 64)) : (zoom / 100) * PX_PER_MM;

  const view: View = useMemo(() => ({ scale, catalog, sample, lang, showSample, label: labelOf, settings }), [scale, catalog, sample, lang, showSample, labelOf, settings]);

  // ---- leaving
  useEffect(() => {
    if (!dirty) return;
    const guard = (e: BeforeUnloadEvent) => e.preventDefault();

    window.addEventListener("beforeunload", guard);

    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);

  // ---- editing helpers
  const spotOf = useCallback(() => ({ x: latest.current.layout.page.width_mm / 2, y: latest.current.layout.page.height_mm / 2 }), []);
  const addLayers = useCallback((layers: Layer[]) => dispatch({ type: "add", layers }), []);

  const upload = useCallback(async (file: File, kind: "background" | "image") => {
    setBusy("upload");
    try {
      return await uploadForm<CertAsset>("/api/v1/cert-assets", file, file.name, { fields: { kind } });
    } catch (e) {
      notifyError(e);

      return null;
    } finally {
      setBusy(null);
    }
  }, []);

  const addBlock = useCallback(
    (key: BlockKey, spot = spotOf()) => {
      if (key === "image") {
        imageTarget.current = { replace: null, spot };
        imageInput.current?.click();

        return;
      }
      addLayers(makeBlock(key, latest.current.layout.layers.map((l) => l.id), spot));
    },
    [addLayers, spotOf],
  );

  async function onImageFile(file: File) {
    const target = imageTarget.current;
    const a = await upload(file, "image");

    if (!a || !target) return;
    if (target.replace) {
      dispatch({ type: "update", ids: [target.replace], fn: (l) => (l.type === "image" ? { ...l, source: { asset: a.id } } : l) });
    } else {
      addLayers(makeBlock("image", latest.current.layout.layers.map((l) => l.id), target.spot, { id: a.id, w: a.width_px, h: a.height_px }));
    }
  }

  async function onBackground(file: File | null) {
    if (!file) return dispatch({ type: "set_background", asset: null });
    const a = await upload(file, "background");

    if (a) dispatch({ type: "set_background", asset: a.id });
  }

  function insertField(key: string) {
    if (editorApi.current) return editorApi.current.insertField(key);
    const cur = latest.current;
    const sel = cur.selection.length === 1 ? cur.layout.layers.find((l) => l.id === cur.selection[0]) : undefined;

    if (sel?.type === "text") {
      dispatch({ type: "update", ids: [sel.id], fn: (l) => (l.type === "text" ? { ...l, content: [...l.content, { field: key }] } : l) });

      return;
    }
    const [layer] = makeBlock("text", cur.layout.layers.map((l) => l.id), spotOf());

    if (layer.type === "text") addLayers([{ ...layer, content: [{ field: key }] }]);
  }

  const commitText = useCallback((id: string, runs: Run[]) => {
    dispatch({ type: "update", ids: [id], fn: (l) => (l.type === "text" ? { ...l, content: runs } : l), key: `text:${id}` });
  }, []);

  // ---- keyboard
  useEffect(() => {
    if (!wide || !canEdit) return;
    const onKey = (e: KeyboardEvent) => {
      if (isEditable(e.target) || document.querySelector('[role="dialog"]')) return;
      const mod = e.metaKey || e.ctrlKey;
      const k = e.key.toLowerCase();

      if (mod && k === "z") {
        e.preventDefault();
        dispatch({ type: e.shiftKey ? "redo" : "undo" });
      } else if (mod && k === "y") {
        e.preventDefault();
        dispatch({ type: "redo" });
      } else if (mod && k === "d") {
        e.preventDefault();
        dispatch({ type: "duplicate" });
      } else if (mod && k === "s") {
        e.preventDefault();
        document.querySelector<HTMLButtonElement>('[data-testid="save"]')?.click();
      } else if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        dispatch({ type: "delete" });
      } else if (e.key === "Escape") {
        dispatch({ type: "select", ids: [] });
      } else {
        const d = nudgeDelta(e.key, e.shiftKey);

        if (d) {
          e.preventDefault();
          dispatch({ type: "nudge", ...d });
        }
      }
    };

    window.addEventListener("keydown", onKey);

    return () => window.removeEventListener("keydown", onKey);
  }, [wide, canEdit]);

  // ---- actions
  async function check(layout: Layout = state.layout) {
    setBusy("check");
    const tab = window.open("", "_blank");

    try {
      const blob = await postForPdf(`/api/v1/cert-templates/${initial.id}/draft-preview?sample=${sample}`, { layout });
      const url = URL.createObjectURL(blob);

      if (tab) tab.location.href = url;
      else saveBlob(blob, `${detail.key}_${sample}.pdf`);
      setTimeout(() => URL.revokeObjectURL(url), 120_000);
    } catch (e) {
      tab?.close();
      notifyError(e);
    } finally {
      setBusy(null);
    }
  }

  async function publish() {
    setBusy("publish");
    try {
      const d = await api<TemplateDetail>(`/api/v1/cert-templates/${initial.id}/publish`, { method: "POST" });

      setConfirm(null);
      notify(`Опубликована версия ${d.latest_version_no}`);
      onReplace(d);
    } catch (e) {
      setConfirm(null);
      notifyError(e);
    } finally {
      setBusy(null);
    }
  }

  async function restore(no: number) {
    setBusy("restore");
    try {
      const d = await api<TemplateDetail>(`/api/v1/cert-templates/${initial.id}/restore/${no}`, { method: "POST", version: detail.version });

      setConfirm(null);
      notify(`Версия ${no} возвращена в черновик`);
      onReplace(d);
    } catch (e) {
      setConfirm(null);
      notifyError(e);
    } finally {
      setBusy(null);
    }
  }

  const back = () => (dirty ? setConfirm("back") : router.push("/settings/certificates"));
  const published = detail.latest_version_no !== null;
  const status = published ? `Опубликовано, версия ${detail.latest_version_no}${detail.has_unpublished_changes ? " · есть неопубликованные изменения" : ""}` : "Черновик · не опубликовано";

  if (!wide)
    return (
      <div className="fixed inset-0 z-40 flex flex-col overflow-y-auto bg-background p-5">
        <button className="mb-4 flex items-center gap-1 self-start text-sm text-brand-text" type="button" onClick={() => router.push("/settings/certificates")}>
          <Icon name="chevron-left" size={18} /> Шаблоны
        </button>
        <h1 className="text-xl font-semibold">{detail.name}</h1>
        <p className="mb-4 text-sm text-default-500">{status}</p>
        <p className="mb-4 rounded-xl bg-content1 p-4 text-default-600" data-testid="phone-notice">
          Конструктор работает на экране шире 1280 px: откройте шаблон на компьютере. Здесь можно посмотреть пример сертификата.
        </p>
        <LoadingButton color="primary" isLoading={busy === "check"} startContent={<Icon name="download" size={18} />} onPress={() => void check(detail.draft)}>
          Скачать пример PDF
        </LoadingButton>
      </div>
    );

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-background" data-testid="constructor">
      {catalog && <style>{fontFaceCss(catalog.fonts)}</style>}
      <header className="flex items-center gap-3 border-b border-divider bg-content1 px-4 py-2">
        <Button isIconOnly aria-label="Назад" variant="light" onPress={back}>
          <Icon name="chevron-left" size={20} />
        </Button>
        <div className="min-w-0 flex-1">
          <input
            aria-label="Название шаблона"
            className="w-full max-w-md truncate rounded-md bg-transparent px-1 text-lg font-semibold outline-none focus:bg-content2"
            data-testid="template-name"
            disabled={!canEdit}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <p className="px-1 text-xs text-default-500" data-testid="status">
            {status}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Switch isSelected={showSample} size="sm" onValueChange={setShowSample}>
            Пример данных
          </Switch>
          {showSample && <Segmented className="!h-10" label="Пример" options={SAMPLES} value={sample} onChange={setSample} />}
        </div>
        <Button data-testid="check" isDisabled={save.pending || busy !== null} isLoading={busy === "check"} variant="flat" onPress={() => void check()}>
          Проверить шаблон
        </Button>
        {canEdit && (
          <>
            <LoadingButton color="primary" data-testid="save" isDisabled={!dirty} isLoading={save.pending} onPress={() => void save.save({ name: name.trim(), lang, draft: state.layout })}>
              Сохранить
            </LoadingButton>
            <LoadingButton
              data-testid="publish"
              isDisabled={dirty || (published && !detail.has_unpublished_changes)}
              isLoading={busy === "publish"}
              title={dirty ? "Сначала сохраните изменения" : undefined}
              variant="flat"
              onPress={() => setConfirm("publish")}
            >
              Опубликовать
            </LoadingButton>
          </>
        )}
      </header>
      <Toolbar canEdit={canEdit} dispatch={dispatch} fit={fitMode} scale={scale} state={state} onFit={() => setZoom(null)} onZoom={setZoom} />
      {failure != null && !save.conflict && (
        <div className="border-b border-danger/30 bg-danger/10 px-4 py-2 text-sm" role="alert">
          <p className="font-medium text-danger">{isApiError(failure) && failure.status === 422 ? "Шаблон не сохранён: в макете есть ошибки" : messageOf(failure)}</p>
          {problems.length > 0 && (
            <ul className="mt-1 list-inside list-disc">
              {problems.map((p, i) => (
                <li key={i}>
                  {p.id ? (
                    <button className="text-left underline" type="button" onClick={() => dispatch({ type: "select", ids: [p.id!] })}>
                      {p.text}
                    </button>
                  ) : (
                    p.text
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <LeftPanel
          busy={busy === "upload"}
          canEdit={canEdit}
          catalog={catalog}
          dispatch={dispatch}
          label={labelOf}
          state={state}
          onAddBlock={(k) => addBlock(k)}
          onBackground={(f) => void onBackground(f)}
          onInsertField={insertField}
        />
        <div ref={stage} className="min-w-0 flex-1 overflow-auto bg-default-200 p-8 dark:bg-black/30" data-testid="stage">
          <div className="mx-auto w-fit">
            <Canvas
              dispatch={dispatch}
              editingId={canEdit ? editingId : null}
              editorApi={editorApi}
              setEditingId={setEditingId}
              state={state}
              view={view}
              onCommit={commitText}
              onDropBlock={(k, spot) => canEdit && addBlock(k, spot)}
            />
          </div>
        </div>
        <RightPanel
          canEdit={canEdit}
          catalog={catalog}
          detail={detail}
          dispatch={dispatch}
          editorApi={editorApi}
          label={labelOf}
          lang={lang}
          name={name}
          state={state}
          onLang={setLang}
          onName={setName}
          onReplaceImage={(id) => {
            imageTarget.current = { replace: id, spot: spotOf() };
            imageInput.current?.click();
          }}
          onRestore={(n) => setConfirm({ restore: n })}
        />
      </div>
      <footer className="flex items-center gap-3 border-t border-divider bg-content1 px-4 py-1.5 text-sm">
        <span className={dirty ? "text-warning-600" : "text-default-500"} data-testid="dirty">
          {dirty ? "Несохранённые изменения" : "Все изменения сохранены"}
        </span>
        <span className="ml-auto flex gap-2">
          {canEdit && (
            <>
              <Button size="sm" variant="light" onPress={() => dispatch({ type: "set_layout", layout: { ...state.layout, background: null, layers: [] } })}>
                Очистить лист
              </Button>
              <Button
                size="sm"
                variant="light"
                onPress={() => dispatch({ type: "set_layout", layout: sampleLayout() })}
              >
                Начать с образца
              </Button>
            </>
          )}
        </span>
      </footer>
      <input
        ref={imageInput}
        accept="image/png,image/jpeg,image/svg+xml"
        className="hidden"
        data-testid="image-file"
        type="file"
        onChange={(e) => {
          const f = e.target.files?.[0];

          if (f) void onImageFile(f);
          e.target.value = "";
        }}
      />
      <ConflictDialog save={save} />
      <ConfirmModal confirmLabel="Выйти" danger isOpen={confirm === "back"} title="Выйти без сохранения?" onClose={() => setConfirm(null)} onConfirm={() => router.push("/settings/certificates")}>
        Несохранённые изменения будут потеряны.
      </ConfirmModal>
      <ConfirmModal confirmLabel="Опубликовать" isLoading={busy === "publish"} isOpen={confirm === "publish"} title="Опубликовать шаблон?" onClose={() => setConfirm(null)} onConfirm={() => void publish()}>
        Новые сертификаты будут выдаваться по этой версии. Уже выданные сертификаты не изменятся.
      </ConfirmModal>
      <ConfirmModal
        confirmLabel="Вернуть"
        isLoading={busy === "restore"}
        isOpen={typeof confirm === "object" && confirm !== null}
        title="Вернуть версию в черновик?"
        onClose={() => setConfirm(null)}
        onConfirm={() => typeof confirm === "object" && confirm && void restore(confirm.restore)}
      >
        Текущий черновик будет заменён выбранной версией{dirty ? ", несохранённые изменения пропадут" : ""}.
      </ConfirmModal>
    </div>
  );
}
