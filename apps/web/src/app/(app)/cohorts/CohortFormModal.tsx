"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import clsx from "clsx";

import { AppModal } from "@/components/AppModal";
import { SelectField } from "@/components/SelectField";
import { useCourses, useInstructors, useRefreshEducation, useRooms } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { api, messageOf } from "@/lib/api";
import { MAX_DATE, MIN_DATE, scheduleProblem, WEEKDAYS } from "@/lib/education";
import { notify } from "@/lib/toast";
import type { CohortRow } from "@/lib/types";

export function CohortFormModal({ cohort, onClose }: { cohort: CohortRow | null; onClose: () => void }) {
  const refresh = useRefreshEducation();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const { data: courses = [] } = useCourses();
  const [courseId, setCourseId] = useState<string | null>(cohort?.course_id ?? null);
  const [branchId, setBranchId] = useState<string | null>(cohort?.branch_id ?? me?.branch?.id ?? null);
  const [instructorId, setInstructorId] = useState<string | null>(cohort?.instructor_id ?? null);
  const [roomId, setRoomId] = useState<string | null>(cohort?.room_id ?? null);
  const [start, setStart] = useState(cohort?.start_date ?? "");
  const [end, setEnd] = useState(cohort?.end_date ?? "");
  const [weekdays, setWeekdays] = useState<number[]>(cohort?.weekdays ?? []);
  const [startTime, setStartTime] = useState(cohort?.start_time ?? "10:00");
  const [endTime, setEndTime] = useState(cohort?.end_time ?? "11:30");
  const [capacity, setCapacity] = useState(String(cohort?.capacity ?? 15));
  const [price, setPrice] = useState(cohort ? String(Number(cohort.price_month)) : "");
  const [error, setError] = useState<string | null>(null);
  const { data: rooms = [] } = useRooms(branchId);
  const { data: instructors = [] } = useInstructors(branchId);

  const cap = Number(capacity);
  const problem = scheduleProblem({ start, end, startTime, endTime, weekdays });
  const valid =
    !!courseId && !!branchId && !!roomId && !!start && !!end && !problem && Number.isInteger(cap) && cap >= 1 && cap <= 100 && Number(price || 0) >= 0;

  const save = useMutation({
    mutationFn: () => {
      const common = {
        instructor_id: instructorId,
        room_id: roomId,
        start_date: start,
        end_date: end,
        weekdays,
        start_time: startTime,
        end_time: endTime,
        capacity: cap,
        price_month: price === "" ? undefined : String(Number(price)),
      };

      return cohort
        ? api(`/api/v1/cohorts/${cohort.id}`, { method: "PATCH", body: common })
        : api("/api/v1/cohorts", { method: "POST", body: { ...common, course_id: courseId, branch_id: branchId } });
    },
    onSuccess: () => {
      void refresh();
      notify(cohort ? "Поток сохранён" : "Поток создан");
      onClose();
    },
    onError: (e) => setError(messageOf(e)),
  });

  const toggleDay = (day: number) =>
    setWeekdays((cur) => (cur.includes(day) ? cur.filter((d) => d !== day) : [...cur, day].sort()));

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <Button color="primary" isDisabled={!valid} isLoading={save.isPending} onPress={() => save.mutate()}>
            {cohort ? "Сохранить" : "Создать"}
          </Button>
        </>
      }
      isOpen
      size="2xl"
      title={cohort ? `Поток ${cohort.code}` : "Новый поток"}
      onClose={onClose}
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) save.mutate();
        }}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <SelectField
            isDisabled={!!cohort}
            isRequired
            label="Курс"
            options={courses.map((c) => ({ key: c.id, label: c.name }))}
            value={courseId}
            onChange={(id) => {
              setCourseId(id);
              const course = courses.find((c) => c.id === id);

              if (!cohort && course && price === "") setPrice(String(Number(course.default_price_month)));
            }}
          />
          <SelectField
            isDisabled={!!cohort || !!me?.branch}
            isRequired
            label="Филиал"
            options={branches.map((b) => ({ key: b.id, label: b.name }))}
            value={branchId}
            onChange={(id) => {
              setBranchId(id);
              setRoomId(null);
              setInstructorId(null);
            }}
          />
          <SelectField
            allLabel="Без инструктора"
            label="Инструктор"
            options={instructors.map((i) => ({ key: i.id, label: i.full_name }))}
            value={instructorId}
            onChange={setInstructorId}
          />
          <SelectField
            isRequired
            label="Аудитория"
            options={rooms.map((r) => ({ key: r.id, label: `${r.name} (${r.capacity})` }))}
            value={roomId}
            onChange={setRoomId}
          />
          <Input
            isRequired
            label="Начало"
            max={MAX_DATE}
            min={MIN_DATE}
            placeholder=" "
            type="date"
            value={start}
            onValueChange={setStart}
          />
          <Input
            isRequired
            label="Конец"
            max={MAX_DATE}
            min={MIN_DATE}
            placeholder=" "
            type="date"
            value={end}
            onValueChange={setEnd}
          />
          <Input isRequired label="Время начала" placeholder=" " type="time" value={startTime} onValueChange={setStartTime} />
          <Input isRequired label="Время конца" placeholder=" " type="time" value={endTime} onValueChange={setEndTime} />
          <Input
            description="От 1 до 100"
            isRequired
            label="Мест в потоке"
            max={100}
            min={1}
            type="number"
            value={capacity}
            onValueChange={setCapacity}
          />
          <Input
            description={cohort ? undefined : "Пусто: цена курса"}
            endContent={<span className="text-xs text-default-500">TJS</span>}
            label="Цена в месяц"
            min={0}
            type="number"
            value={price}
            onValueChange={setPrice}
          />
        </div>
        <fieldset>
          <legend className="mb-2 text-sm text-default-600">Дни занятий</legend>
          <div className="flex flex-wrap gap-2">
            {WEEKDAYS.map((label, i) => (
              <button
                key={label}
                aria-pressed={weekdays.includes(i + 1)}
                className={clsx(
                  "h-10 min-w-12 rounded-xl border px-3 text-sm font-medium transition-colors",
                  weekdays.includes(i + 1)
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-divider bg-content1 text-default-600 hover:bg-default-100",
                )}
                type="button"
                onClick={() => toggleDay(i + 1)}
              >
                {label}
              </button>
            ))}
          </div>
        </fieldset>
        {problem && (
          <p className="text-sm text-warning-600 dark:text-warning" role="status">
            {problem}
          </p>
        )}
        {cohort && (
          <p className="text-xs text-default-500">
            Если изменить даты, дни, время или аудиторию, будущие уроки пересоздаются. Прошедшие остаются как были.
          </p>
        )}
        {error && (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </form>
    </AppModal>
  );
}
