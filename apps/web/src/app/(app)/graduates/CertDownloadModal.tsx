"use client";

import { useState } from "react";
import { Button } from "@heroui/button";

import { AppModal } from "@/components/AppModal";
import { LoadingButton } from "@/components/LoadingButton";
import { SelectField } from "@/components/SelectField";
import { getFile, saveBlob, type GraduateCertTemplates } from "@/hooks/certs";
import { notifyError } from "@/lib/toast";

const LANG_LABEL: Record<string, string> = { ru: "Русский", en: "English", tg: "Тоҷикӣ" };

export function CertDownloadModal({
  enrollmentId,
  fallbackName,
  student,
  data,
  onClose,
}: {
  enrollmentId: string;
  fallbackName: string;
  student: string;
  data: GraduateCertTemplates;
  onClose: () => void;
}) {
  const [id, setId] = useState<string | null>(data.default_template_id ?? data.templates[0]?.id ?? null);
  const [busy, setBusy] = useState(false);
  const options = data.templates.map((t) => ({ key: t.id, label: `${t.name} · ${LANG_LABEL[t.lang] ?? t.lang}` }));

  async function download() {
    if (!id) return;
    setBusy(true);
    try {
      const { blob, name } = await getFile(`/api/v1/graduates/${enrollmentId}/certificate/pdf?template_id=${id}`);

      saveBlob(blob, name ?? fallbackName);
      onClose();
    } catch (e) {
      notifyError(e);
      setBusy(false);
    }
  }

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!id} isLoading={busy} onPress={() => void download()}>
            Скачать
          </LoadingButton>
        </>
      }
      isOpen
      size="md"
      title="Скачать сертификат"
      onClose={onClose}
    >
      <div className="space-y-3">
        <p className="text-sm text-default-500">Студент: {student}. Выберите шаблон сертификата.</p>
        <SelectField label="Шаблон" options={options} value={id} onChange={setId} />
      </div>
    </AppModal>
  );
}
