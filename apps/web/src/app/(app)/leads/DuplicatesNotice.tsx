"use client";

import Link from "next/link";
import { Button } from "@heroui/button";

import { AppModal } from "@/components/AppModal";
import type { Duplicates } from "@/lib/sales-types";

/** The lead is saved; this says the phone is already known, with links. It never blocks. */
export function DuplicatesNotice({
  name,
  duplicates,
  onClose,
}: {
  name: string;
  duplicates: Duplicates;
  onClose: () => void;
}) {
  return (
    <AppModal
      footer={
        <Button color="primary" onPress={onClose}>
          Понятно
        </Button>
      }
      isOpen
      size="md"
      title="Этот телефон уже есть"
      onClose={onClose}
    >
      <div className="space-y-3 text-sm">
        <p>
          Лид «{name}» сохранён. Люди с таким же номером уже есть в системе — возможно, это тот же человек, который
          вернулся.
        </p>
        {duplicates.students.length > 0 && (
          <div>
            <div className="mb-1 text-xs text-default-500">Студенты</div>
            <ul className="space-y-1">
              {duplicates.students.map((s) => (
                <li key={s.id}>
                  <Link className="text-brand-text underline" href={`/students/${s.id}`}>
                    {s.full_name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
        {duplicates.leads.length > 0 && (
          <div>
            <div className="mb-1 text-xs text-default-500">Другие лиды</div>
            <ul className="space-y-1">
              {duplicates.leads.map((l) => (
                <li key={l.id}>
                  {l.full_name} <span className="text-default-500">· {l.status}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </AppModal>
  );
}
