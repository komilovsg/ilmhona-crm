import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";

/** The import's «check this» flag with its reason; a manager can clear it (`onClear`). */
export function ReviewChip({
  reason,
  onClear,
  clearing = false,
}: {
  reason: string | null;
  onClear?: () => void;
  clearing?: boolean;
}) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <Chip color="warning" size="sm" title={reason ?? undefined} variant="flat">
        Проверить
      </Chip>
      {reason && <span className="text-xs text-default-500">{reason}</span>}
      {onClear && (
        <Button isLoading={clearing} size="sm" variant="light" onPress={onClear}>
          Снять отметку
        </Button>
      )}
    </span>
  );
}
