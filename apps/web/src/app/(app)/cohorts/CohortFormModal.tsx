"use client";

import { DateField } from "@/components/DateField";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import { Select, SelectItem } from "@heroui/select";
import clsx from "clsx";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { SelectField } from "@/components/SelectField";
import { useDonorOptions } from "@/hooks/donors";
import { useCourses, useInstructors, useRefreshEducation, useRooms } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import { MAX_DATE, MIN_DATE, scheduleProblem, WEEKDAYS, endDateOf, monthsOf } from "@/lib/education";
import { FUNDINGS, fundingProblem, withDonors } from "@/lib/funding";
import { useOverlayMotion } from "@/lib/motion";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";
import type { CohortRow, Funding } from "@/lib/types";
import { LoadingButton } from "@/components/LoadingButton";

const FIELDS = ["instructor_id", "room_id", "start_date", "end_date", "start_time", "end_time", "capacity", "price_month", "donor_ids"];

/** Where a new cohort starts when it is created from a free cell of the room board. */
export type CohortPreset = { branch_id: string; room_id: string; start_date: string; weekday: number; start_time: string; end_time: string };

export function CohortFormModal({
  cohort,
  preset,
  onClose,
}: {
  cohort: CohortRow | null;
  preset?: CohortPreset;
  onClose: () => void;
}) {
  const refresh = useRefreshEducation();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const { data: courses = [] } = useCourses();
  const [courseId, setCourseId] = useState<string | null>(cohort?.course_id ?? null);
  const [branchId, setBranchId] = useState<string | null>(cohort?.branch_id ?? preset?.branch_id ?? me?.branch?.id ?? null);
  const [instructorId, setInstructorId] = useState<string | null>(cohort?.instructor_id ?? null);
  const [roomId, setRoomId] = useState<string | null>(cohort?.room_id ?? preset?.room_id ?? null);
  const [start, setStart] = useState(cohort?.start_date ?? preset?.start_date ?? "");
  const [end, setEnd] = useState(cohort?.end_date ?? "");
  const [months, setMonths] = useState(cohort ? String(monthsOf(cohort.start_date, cohort.end_date) ?? "") : "");
  // the end follows the start and the length; a hand-typed end stays until one of them changes
  const plan = (nextStart: string, nextMonths: string) => {
    const n = Number(nextMonths);

    if (nextStart && Number.isInteger(n) && n >= 1 && n <= 36) setEnd(endDateOf(nextStart, n));
  };
  const [weekdays, setWeekdays] = useState<number[]>(cohort?.weekdays ?? (preset ? [preset.weekday] : []));
  const [startTime, setStartTime] = useState(cohort?.start_time ?? preset?.start_time ?? "10:00");
  const [endTime, setEndTime] = useState(cohort?.end_time ?? preset?.end_time ?? "11:30");
  const [capacity, setCapacity] = useState(String(cohort?.capacity ?? 15));
  const [price, setPrice] = useState(cohort ? String(Number(cohort.price_month)) : "");
  const [funding, setFunding] = useState<Funding>(cohort?.funding ?? "платный");
  const [donorIds, setDonorIds] = useState<string[]>(cohort?.donors.map((d) => d.id).sort() ?? []);
  const { data: donorOptions = [] } = useDonorOptions();
  const overlayMotion = useOverlayMotion();
  // archived donors are offered only when the cohort already has them
  const donorChoices = donorOptions.filter((d) => !d.archived || donorIds.includes(d.id));
  const free = funding === "бесплатный";
  const [failed, setFailed] = useState<{ error: unknown; sig: string } | null>(null);
  const { data: rooms = [] } = useRooms(branchId);
  const { data: instructors = [] } = useInstructors(branchId);
  // the cohort's own room is always an option (an imported «Без аудитории (G-NNN)» room may be
  // missing from the branch list, or the list is still loading): the select never holds an
  // unknown key
  const roomOptions = rooms.map((r) => ({ key: r.id, label: `${r.name} (${r.capacity})` }));
  if (cohort && roomId === cohort.room_id && !rooms.some((r) => r.id === roomId))
    roomOptions.unshift({ key: cohort.room_id, label: cohort.room_name });

  const cap = Number(capacity);
  const problem = scheduleProblem({ start, end, startTime, endTime, weekdays }) ?? fundingProblem(funding, donorIds);
  const valid =
    !!courseId && !!branchId && !!roomId && !!start && !!end && !problem && Number.isInteger(cap) && cap >= 1 && cap <= 100 && Number(price || 0) >= 0;

  const values = {
    instructor_id: instructorId,
    room_id: roomId,
    start_date: start,
    end_date: end,
    weekdays,
    start_time: startTime,
    end_time: endTime,
    capacity: cap,
    price_month: free ? "0" : price === "" ? "" : String(Number(price)),
    funding,
    donor_ids: withDonors(funding) ? donorIds : [],
  };
  // A server error belongs to the values that were sent: any edit hides it, and so does a client hint.
  const sig = JSON.stringify([courseId, branchId, values]);
  const body = (v: Partial<typeof values>) => ({ ...v, price_month: v.price_month === "" ? undefined : v.price_month });
  const done = () => {
    void refresh();
    notify(cohort ? "Поток сохранён" : "Поток создан");
    onClose();
  };
  const create = useMutation({
    mutationFn: () =>
      api("/api/v1/cohorts", { method: "POST", body: { ...body(values), course_id: courseId, branch_id: branchId } }),
    onSuccess: done,
    onError: (e) => setFailed({ error: e, sig }),
  });
  const edit = useVersionedSave({
    record: cohort,
    values,
    toValues: (c) => ({
      instructor_id: c.instructor_id,
      room_id: c.room_id as string | null,
      start_date: c.start_date,
      end_date: c.end_date,
      weekdays: c.weekdays,
      start_time: c.start_time,
      end_time: c.end_time,
      capacity: c.capacity,
      price_month: String(Number(c.price_month)),
      funding: c.funding,
      donor_ids: c.donors.map((d) => d.id).sort(),
    }),
    apply: (v) => {
      setInstructorId(v.instructor_id);
      setRoomId(v.room_id);
      setStart(v.start_date);
      setEnd(v.end_date);
      setWeekdays(v.weekdays);
      setStartTime(v.start_time);
      setEndTime(v.end_time);
      setCapacity(String(v.capacity));
      setPrice(v.price_month);
      setFunding(v.funding);
      setDonorIds(v.donor_ids);
    },
    request: (changed, version) =>
      api(`/api/v1/cohorts/${cohort?.id}`, { method: "PATCH", body: body(changed), version }),
    labels: {
      instructor_id: "Инструктор",
      room_id: "Аудитория",
      start_date: "Начало",
      end_date: "Конец",
      weekdays: "Дни занятий",
      start_time: "Время начала",
      end_time: "Время конца",
      capacity: "Мест в потоке",
      price_month: "Цена в месяц",
      funding: "Финансирование",
      donor_ids: "Доноры",
    },
    show: {
      instructor_id: (id: string | null) => instructors.find((i) => i.id === id)?.full_name ?? "Без инструктора",
      room_id: (id: string | null) => rooms.find((r) => r.id === id)?.name ?? "—",
      weekdays: (days: number[]) => days.map((d) => WEEKDAYS[d - 1]).join(", ") || "—",
      donor_ids: (ids: string[]) => ids.map((id) => donorOptions.find((d) => d.id === id)?.name ?? "—").join(", ") || "—",
    },
    onSaved: done,
  });
  const fe = useFieldErrors(cohort ? edit.failure : (failed?.error ?? null), FIELDS);
  const message = cohort || failed?.sig === sig ? fe.message : null;
  const submit = useSubmit(() => (cohort ? edit.save(values) : create.mutateAsync()), !valid);

  const toggleDay = (day: number) =>
    setWeekdays((cur) => (cur.includes(day) ? cur.filter((d) => d !== day) : [...cur, day].sort()));

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={create.isPending || edit.pending} onPress={() => submit()}>
            {cohort ? "Сохранить" : "Создать"}
          </LoadingButton>
        </>
      }
      isOpen
      size="2xl"
      title={cohort ? `Поток ${cohort.code}` : "Новый поток"}
      onClose={onClose}
    >
      <form
        className="space-y-4"
        onSubmit={submit}
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
              if (!cohort && course && months === "") {
                setMonths(String(course.duration_months));
                plan(start, String(course.duration_months));
              }
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
            {...fe.hint("instructor_id")}
            onChange={(v) => {
              fe.clear("instructor_id");
              setInstructorId(v);
            }}
          />
          <SelectField
            isRequired
            label="Аудитория"
            options={roomOptions}
            value={roomId}
            {...fe.hint("room_id")}
            onChange={(v) => {
              fe.clear("room_id");
              setRoomId(v);
            }}
          />
          <DateField
            isRequired
            label="Начало"
            max={MAX_DATE}
            min={MIN_DATE}
            value={start}
            {...fe.field("start_date", (v: string) => {
              setStart(v);
              plan(v, months);
            })}
          />
          <Input
            description="Дата конца считается сама; её можно поправить"
            label="Длительность, мес."
            max={36}
            min={1}
            placeholder=" "
            type="number"
            value={months}
            onValueChange={(v) => {
              setMonths(v);
              plan(start, v);
            }}
          />
          <DateField
            isRequired
            label="Конец"
            max={MAX_DATE}
            min={MIN_DATE}
            value={end}
            {...fe.field("end_date", (v: string) => {
              setEnd(v);
              setMonths(String(monthsOf(start, v) ?? ""));
            })}
          />
          <Input isRequired label="Время начала" placeholder=" " type="time" value={startTime} {...fe.field("start_time", setStartTime)} />
          <Input isRequired label="Время конца" placeholder=" " type="time" value={endTime} {...fe.field("end_time", setEndTime)} />
          <Input
            description="От 1 до 100"
            isRequired
            label="Мест в потоке"
            max={100}
            min={1}
            type="number"
            value={capacity}
            {...fe.field("capacity", setCapacity)}
          />
          <Input
            description={cohort || free ? undefined : "Пусто: цена курса"}
            endContent={<span className="text-xs text-default-600">TJS</span>}
            isDisabled={free}
            label="Цена в месяц"
            min={0}
            type="number"
            value={free ? "0" : price}
            {...fe.field("price_month", setPrice)}
          />
          <SelectField
            isRequired
            label="Финансирование"
            options={FUNDINGS}
            value={funding}
            onChange={(v) => v && setFunding(v as Funding)}
          />
          {withDonors(funding) && (
            <Select
              classNames={{ value: "truncate" }}
              errorMessage={fe.hint("donor_ids").errorMessage}
              isInvalid={fe.hint("donor_ids").isInvalid}
              isRequired
              items={donorChoices}
              label="Доноры"
              popoverProps={{ motionProps: overlayMotion }}
              selectedKeys={donorIds}
              selectionMode="multiple"
              onSelectionChange={(keys) => {
                fe.clear("donor_ids");
                setDonorIds([...keys].map(String).sort());
              }}
            >
              {(d) => (
                <SelectItem key={d.id} classNames={{ title: "whitespace-normal break-words" }}>
                  {d.name}
                </SelectItem>
              )}
            </Select>
          )}
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
        {!problem && message && (
          <p className="text-sm text-danger" role="alert">
            {message}
          </p>
        )}
      </form>
      <ConflictDialog save={edit} />
    </AppModal>
  );
}
