import { Chip } from "@heroui/chip";

import { plural } from "@/lib/dash";
import { cohortTone, studentTone, type Tone } from "@/lib/education";

function Tinted({ tone, label }: { tone: Tone; label: string }) {
  return (
    <Chip color={tone} size="sm" variant="flat">
      {label}
    </Chip>
  );
}

export function CohortStatus({ status }: { status: string }) {
  return <Tinted label={status} tone={cohortTone(status)} />;
}

/** Student or enrollment status (same words, same colours). */
export function PersonStatus({ status }: { status: string }) {
  return <Tinted label={status} tone={studentTone(status)} />;
}

/** «Срок вышел»: активный поток после даты конца, ещё не завершённый. */
export function OverdueChip() {
  return (
    <Chip color="warning" size="sm" title="Дата конца прошла, поток ещё не завершён" variant="flat">
      Срок вышел
    </Chip>
  );
}

const ddmm = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

/** Нет отметок давно; «закроется» только когда суперадмин включил автозакрытие. */
export function StaleChip({ stale }: { stale: { idle_days: number; closes_on: string | null } }) {
  return (
    <Chip
      classNames={{ base: "h-auto max-w-full py-0.5", content: "whitespace-normal" }}
      color="warning"
      size="sm"
      title={stale.closes_on ? "Отметьте посещаемость, иначе поток закроется автоматически" : "Отметьте посещаемость"}
      variant="flat"
    >
      Нет отметок {stale.idle_days} {plural(stale.idle_days, "день", "дня", "дней")}{stale.closes_on ? ` — закроется ${ddmm(stale.closes_on)}` : ""}
    </Chip>
  );
}
