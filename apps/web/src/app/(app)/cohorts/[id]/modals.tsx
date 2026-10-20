"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import { Spinner } from "@heroui/spinner";

import { AppModal } from "@/components/AppModal";
import { Segmented } from "@/components/Segmented";
import { SelectField } from "@/components/SelectField";
import { PersonStatus } from "@/components/StatusChip";
import { useRefreshEducation, useRooms } from "@/hooks/education";
import { useMe } from "@/hooks/queries";
import { api, messageOf } from "@/lib/api";
import { MAX_DATE, MIN_DATE, timeProblem } from "@/lib/education";
import { can } from "@/lib/permissions";
import { notify } from "@/lib/toast";
import type { CohortRow, LessonRow, Paged, StudentRow } from "@/lib/types";

/** Add a lesson by hand (no `lesson`) or move one (with `lesson`). A busy room answers 409 with the other cohort's name. */
export function LessonFormModal({
  cohort,
  lesson,
  onClose,
}: {
  cohort: CohortRow;
  lesson: LessonRow | null;
  onClose: () => void;
}) {
  const refresh = useRefreshEducation();
  const { data: rooms = [] } = useRooms(cohort.branch_id);
  const [date, setDate] = useState(lesson?.date ?? "");
  const [start, setStart] = useState(lesson?.start ?? cohort.start_time);
  const [end, setEnd] = useState(lesson?.end ?? cohort.end_time);
  const [roomId, setRoomId] = useState<string | null>(lesson?.room_id ?? cohort.room_id);
  const [error, setError] = useState<string | null>(null);
  const problem = timeProblem(start, end);
  const valid = !!date && !!roomId && !problem && date >= MIN_DATE && date <= MAX_DATE;

  const save = useMutation({
    mutationFn: () => {
      const body = { date, start_time: start, end_time: end, room_id: roomId };

      return lesson
        ? api(`/api/v1/lessons/${lesson.id}`, { method: "PATCH", body })
        : api(`/api/v1/cohorts/${cohort.id}/lessons`, { method: "POST", body });
    },
    onSuccess: () => {
      void refresh();
      notify(lesson ? "Урок перенесён" : "Урок добавлен");
      onClose();
    },
    onError: (e) => setError(messageOf(e)),
  });

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <Button color="primary" isDisabled={!valid} isLoading={save.isPending} onPress={() => save.mutate()}>
            {lesson ? "Перенести" : "Добавить"}
          </Button>
        </>
      }
      isOpen
      size="md"
      title={lesson ? "Перенести урок" : "Добавить урок"}
      onClose={onClose}
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) save.mutate();
        }}
      >
        <Input isRequired label="Дата" max={MAX_DATE} min={MIN_DATE} placeholder=" " type="date" value={date} onValueChange={setDate} />
        <div className="grid grid-cols-2 gap-3">
          <Input isRequired label="Начало" placeholder=" " type="time" value={start} onValueChange={setStart} />
          <Input isRequired label="Конец" placeholder=" " type="time" value={end} onValueChange={setEnd} />
        </div>
        <SelectField
          isRequired
          label="Аудитория"
          options={rooms.map((r) => ({ key: r.id, label: r.name }))}
          value={roomId}
          onChange={setRoomId}
        />
        {problem && (
          <p className="text-sm text-warning-600 dark:text-warning" role="status">
            {problem}
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

type Mode = "existing" | "new";

/** Enrol an existing student (search) or create one and enrol them in one step. */
export function EnrollModal({ cohort, onClose }: { cohort: CohortRow; onClose: () => void }) {
  const refresh = useRefreshEducation();
  const { data: me } = useMe();
  const canSearch = can(me?.permissions, "students", "view");
  const canCreate = can(me?.permissions, "students", "change");
  const [mode, setMode] = useState<Mode>(canSearch ? "existing" : "new");
  const [q, setQ] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [gender, setGender] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const term = q.trim();

  const found = useQuery({
    queryKey: ["students", "pick", term],
    queryFn: () => api<Paged<StudentRow>>("/api/v1/students", { params: { q: term, page_size: "8" } }),
    enabled: mode === "existing" && canSearch && term.length >= 2,
  });

  const enroll = useMutation({
    mutationFn: (body: { student_id: string } | { new_student: { full_name: string; phone: string | null; gender: string | null } }) =>
      api(`/api/v1/cohorts/${cohort.id}/enrollments`, { method: "POST", body }),
    onSuccess: () => {
      void refresh();
      notify("Студент зачислен");
      onClose();
    },
    onError: (e) => setError(messageOf(e)),
  });

  const modes = [
    ...(canSearch ? [{ key: "existing" as const, label: "Найти студента" }] : []),
    ...(canCreate ? [{ key: "new" as const, label: "Новый студент" }] : []),
  ];

  return (
    <AppModal
      footer={
        mode === "new" ? (
          <>
            <Button variant="light" onPress={onClose}>
              Отмена
            </Button>
            <Button
              color="primary"
              isDisabled={!name.trim()}
              isLoading={enroll.isPending}
              onPress={() => enroll.mutate({ new_student: { full_name: name, phone: phone.trim() || null, gender } })}
            >
              Создать и зачислить
            </Button>
          </>
        ) : (
          <Button variant="light" onPress={onClose}>
            Закрыть
          </Button>
        )
      }
      isOpen
      size="md"
      title={`Зачислить в ${cohort.code}`}
      onClose={onClose}
    >
      <div className="space-y-4">
        {modes.length > 1 && <Segmented label="Способ" options={modes} value={mode} onChange={setMode} />}
        {mode === "existing" ? (
          <>
            <Input
              autoFocus
              isClearable
              label="Имя или телефон"
              value={q}
              onClear={() => setQ("")}
              onValueChange={setQ}
            />
            {term.length < 2 ? (
              <p className="text-sm text-default-500">Введите хотя бы 2 символа.</p>
            ) : found.isPending ? (
              <Spinner className="flex justify-center py-4" />
            ) : found.data?.items.length === 0 ? (
              <p className="text-sm text-default-500">Никого не найдено.</p>
            ) : (
              <ul className="divide-y divide-divider rounded-xl border border-divider">
                {found.data?.items.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 p-3">
                    <div className="min-w-0">
                      <div className="truncate font-medium">{s.full_name}</div>
                      <div className="text-xs text-default-500">{s.phone ?? "без телефона"}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <PersonStatus status={s.status} />
                      <Button color="primary" isLoading={enroll.isPending} size="sm" onPress={() => enroll.mutate({ student_id: s.id })}>
                        Зачислить
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) enroll.mutate({ new_student: { full_name: name, phone: phone.trim() || null, gender } });
            }}
          >
            <Input isRequired label="ФИО" value={name} onValueChange={setName} />
            <Input label="Телефон" type="tel" value={phone} onValueChange={setPhone} />
            <SelectField
              allLabel="Не указан"
              label="Пол"
              options={[
                { key: "male", label: "Мужской" },
                { key: "female", label: "Женский" },
              ]}
              value={gender}
              onChange={setGender}
            />
          </form>
        )}
        {error && (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </div>
    </AppModal>
  );
}
