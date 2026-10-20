"use client";

import { Button } from "@heroui/button";

import { AppModal } from "@/components/AppModal";
import type { VersionedSave } from "@/hooks/useVersionedSave";

/**
 * «Запись изменил {ФИО} в {HH:MM}. Ваши изменения: … Сейчас в базе: …». Shown over the form
 * after a 409 `stale_version`; the form stays open behind it. One dialog for all edit forms.
 */
export function ConflictDialog({ save }: { save: Pick<VersionedSave, "conflict" | "retry" | "cancel" | "pending"> }) {
  const { conflict } = save;

  if (!conflict) return null;

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={save.cancel}>
            Отменить
          </Button>
          <Button color="primary" isLoading={save.pending} onPress={() => void save.retry()}>
            Обновить и повторить
          </Button>
        </>
      }
      isOpen
      size="md"
      title="Запись уже изменили"
      onClose={save.cancel}
    >
      <div className="space-y-4 text-sm">
        <p>{conflict.title}</p>
        <section>
          <h3 className="mb-1 font-medium">Ваши изменения</h3>
          <ul className="space-y-0.5" aria-label="Ваши изменения">
            {conflict.lines.map((l) => (
              <li key={l.label}>
                <span className="text-default-500">{l.label}:</span> {l.mine}
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h3 className="mb-1 font-medium">Сейчас в базе</h3>
          <ul className="space-y-0.5" aria-label="Сейчас в базе">
            {conflict.lines.map((l) => (
              <li key={l.label}>
                <span className="text-default-500">{l.label}:</span> {l.theirs}
              </li>
            ))}
          </ul>
        </section>
        <p className="text-xs text-default-500">
          «Обновить и повторить» загрузит запись заново, наложит на неё ваши изменения и сохранит. Остальные поля
          останутся такими, как их сохранил другой пользователь.
        </p>
      </div>
    </AppModal>
  );
}
