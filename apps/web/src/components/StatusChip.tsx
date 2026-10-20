import { Chip } from "@heroui/chip";

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
