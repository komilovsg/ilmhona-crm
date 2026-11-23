"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";

import { AppModal } from "@/components/AppModal";
import { Icon } from "@/components/Icon";
import { SelectField } from "@/components/SelectField";
import { api } from "@/lib/api";
import { dayTitle, isoWeekday } from "@/lib/education";
import { lazyModal } from "@/lib/lazy-modal";
import { clock, minutes } from "@/lib/schedule-board";
import type { CohortRow, Paged, Room } from "@/lib/types";

const CohortFormModal = lazyModal(() => import("../cohorts/CohortFormModal").then((m) => m.CohortFormModal));
const LessonFormModal = lazyModal(() => import("../cohorts/[id]/modals").then((m) => m.LessonFormModal));

/** A free cell of the board: the room, the day and the half hour that was clicked. */
export type Slot = { room: Room; date: string; start: string; x: number; y: number };

const LESSON_MINUTES = 90;
const endOf = (start: string) => clock(Math.min(minutes(start) + LESSON_MINUTES, 22 * 60));

/** Which cohort gets the one-off lesson: the running and the recruiting ones of the room's branch. */
function PickCohort({ slot, onPick, onClose }: { slot: Slot; onPick: (c: CohortRow) => void; onClose: () => void }) {
  const [id, setId] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["cohorts", "open", slot.room.branch_id],
    queryFn: () =>
      api<Paged<CohortRow>>("/api/v1/cohorts", { params: { branch_id: slot.room.branch_id, page_size: "100" } }),
  });
  const open = (list.data?.items ?? []).filter((c) => c.status === "набор" || c.status === "активный");
  const picked = open.find((c) => c.id === id);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <Button color="primary" isDisabled={!picked} onPress={() => picked && onPick(picked)}>
            Дальше
          </Button>
        </>
      }
      isOpen
      size="md"
      title="Разовый урок"
      onClose={onClose}
    >
      <p className="mb-4 text-sm text-default-600">
        {slot.room.name} · {dayTitle(slot.date)} · {slot.start}. Урок добавится в расписание выбранного потока.
      </p>
      <SelectField
        isRequired
        label="Поток"
        options={open.map((c) => ({ key: c.id, label: `${c.code} · ${c.course_name}` }))}
        value={id}
        onChange={setId}
      />
      {list.isSuccess && open.length === 0 && (
        <p className="mt-3 text-sm text-default-500">В этом филиале нет потоков в наборе или в работе.</p>
      )}
    </AppModal>
  );
}

/** The menu of a clicked free cell and the forms it opens. */
export function SlotActions({ slot, onClose }: { slot: Slot; onClose: () => void }) {
  const [step, setStep] = useState<"menu" | "cohort" | "pick" | CohortRow>("menu");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && step === "menu" && onClose();

    window.addEventListener("keydown", onKey);

    return () => window.removeEventListener("keydown", onKey);
  }, [step, onClose]);

  const end = endOf(slot.start);

  if (step === "cohort")
    return (
      <CohortFormModal
        cohort={null}
        preset={{
          branch_id: slot.room.branch_id,
          room_id: slot.room.id,
          start_date: slot.date,
          weekday: isoWeekday(slot.date),
          start_time: slot.start,
          end_time: end,
        }}
        onClose={onClose}
      />
    );
  if (step === "pick") return <PickCohort slot={slot} onClose={onClose} onPick={setStep} />;
  if (step !== "menu")
    return (
      <LessonFormModal
        cohort={step}
        lesson={null}
        preset={{ date: slot.date, start: slot.start, end, room_id: slot.room.id }}
        onClose={onClose}
      />
    );

  const item = "flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-left text-sm hover:bg-default-100";

  return (
    <>
      <div aria-hidden className="fixed inset-0 z-40" onClick={onClose} />
      <div
        className="surface-card fixed z-50 w-64 bg-content1/85 p-1.5 shadow-xl backdrop-blur-md"
        role="menu"
        style={{ left: Math.min(slot.x, window.innerWidth - 272), top: Math.min(slot.y, window.innerHeight - 170) }}
      >
        <div className="px-3 pb-2 pt-1 text-xs text-default-500">
          {slot.room.name} · {dayTitle(slot.date)} · {slot.start}
        </div>
        <button autoFocus className={item} role="menuitem" type="button" onClick={() => setStep("cohort")}>
          <Icon name="plus" size={16} />
          <span>
            Новый поток
            <span className="block text-xs text-default-500">по дням недели, на весь срок</span>
          </span>
        </button>
        <button className={item} role="menuitem" type="button" onClick={() => setStep("pick")}>
          <Icon name="plus" size={16} />
          <span>
            Разовый урок
            <span className="block text-xs text-default-500">одно занятие потока</span>
          </span>
        </button>
      </div>
    </>
  );
}
