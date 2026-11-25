"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@heroui/button";

import { AppModal } from "@/components/AppModal";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { fetchCertPdf, saveBytes } from "@/hooks/certs";
import { fetchAll, mergePdfs, progressLabel, zipPdfs, type PdfFile } from "@/lib/certs";
import { messageOf } from "@/lib/api";

/**
 * Downloads the certificates' PDFs one by one («12 из 18»), then offers them as one PDF (all pages in
 * the order given) or as a ZIP of separate files named as the API names them.
 */
export function CertPackageModal({ ids, title, onClose }: { ids: string[]; title: string; onClose: () => void }) {
  const [progress, setProgress] = useState({ done: 0, total: ids.length });
  const [files, setFiles] = useState<PdfFile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"merged" | "zip" | null>(null);
  const [attempt, setAttempt] = useState(0);
  const started = useRef<number | null>(null);

  useEffect(() => {
    // one run per attempt (the effect runs twice in dev strict mode)
    if (started.current === attempt) return;
    started.current = attempt;
    void fetchAll(ids, fetchCertPdf, (done, total) => setProgress({ done, total }))
      .then(setFiles)
      .catch((e) => setError(messageOf(e)));
  }, [ids, attempt]);

  async function merged() {
    if (!files) return;
    setBusy("merged");
    try {
      saveBytes(await mergePdfs(files), "certificates.pdf", "application/pdf");
    } catch {
      setError("Не удалось объединить файлы в один PDF.");
    } finally {
      setBusy(null);
    }
  }

  function zip() {
    if (!files) return;
    setBusy("zip");
    try {
      saveBytes(zipPdfs(files), "certificates.zip", "application/zip");
    } finally {
      setBusy(null);
    }
  }

  const percent = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <AppModal
      footer={
        <Button variant="light" onPress={onClose}>
          Закрыть
        </Button>
      }
      guard={false}
      isOpen
      size="md"
      title={title}
      onClose={onClose}
    >
      <div className="space-y-4">
        {!files && !error && (
          <div aria-live="polite" role="status">
            <p className="mb-2 text-sm">Загружаем сертификаты: {progressLabel(progress.done, progress.total)}</p>
            <div className="h-2 overflow-hidden rounded-full bg-content2">
              <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${percent}%` }} />
            </div>
          </div>
        )}
        {error && (
          <div className="space-y-3" role="alert">
            <p className="text-danger">{error}</p>
            <Button
              color="primary"
              variant="flat"
              onPress={() => {
                setError(null);
                setProgress({ done: 0, total: ids.length });
                setAttempt((n) => n + 1);
              }}
            >
              Повторить
            </Button>
          </div>
        )}
        {files && (
          <>
            <p className="text-sm text-default-600">Готово: {progressLabel(files.length, files.length)}. Как скачать?</p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <LoadingButton color="primary" isLoading={busy === "merged"} startContent={<Icon name="download" size={18} />} onPress={() => void merged()}>
                Один PDF
              </LoadingButton>
              <LoadingButton isLoading={busy === "zip"} startContent={<Icon name="download" size={18} />} variant="flat" onPress={zip}>
                ZIP отдельных файлов
              </LoadingButton>
            </div>
          </>
        )}
      </div>
    </AppModal>
  );
}
