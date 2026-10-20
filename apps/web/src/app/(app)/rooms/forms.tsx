"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { SelectField } from "@/components/SelectField";
import { useRefreshEducation } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api, messageOf } from "@/lib/api";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";
import type { Course, Room } from "@/lib/types";

export function RoomFormModal({ room, onClose }: { room: Room | null; onClose: () => void }) {
  const refresh = useRefreshEducation();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const [name, setName] = useState(room?.name ?? "");
  const [capacity, setCapacity] = useState(String(room?.capacity ?? 20));
  const [branchId, setBranchId] = useState<string | null>(room?.branch_id ?? me?.branch?.id ?? null);
  const [error, setError] = useState<string | null>(null);
  const size = Number(capacity);
  const valid = name.trim() && Number.isInteger(size) && size >= 1 && size <= 100 && (room || branchId);

  const values = { name: name.trim(), capacity: size };
  const done = () => {
    void refresh();
    notify(room ? "Аудитория сохранена" : "Аудитория добавлена");
    onClose();
  };
  const create = useMutation({
    mutationFn: () => api("/api/v1/rooms", { method: "POST", body: { ...values, branch_id: branchId } }),
    onSuccess: done,
    onError: (e) => setError(messageOf(e)),
  });
  const edit = useVersionedSave({
    record: room,
    values,
    toValues: (r) => ({ name: r.name, capacity: r.capacity }),
    apply: (v) => {
      setName(v.name);
      setCapacity(String(v.capacity));
    },
    request: (changed, version) => api(`/api/v1/rooms/${room?.id}`, { method: "PATCH", body: changed, version }),
    labels: { name: "Название", capacity: "Вместимость" },
    onSaved: done,
  });
  const submit = useSubmit(() => (room ? edit.save(values) : create.mutateAsync()), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <Button color="primary" isDisabled={!valid} isLoading={create.isPending || edit.pending} onPress={() => submit()}>
            {room ? "Сохранить" : "Добавить"}
          </Button>
        </>
      }
      isOpen
      size="md"
      title={room ? "Аудитория" : "Новая аудитория"}
      onClose={onClose}
    >
      <form
        className="space-y-4"
        onSubmit={submit}
      >
        <SelectField
          isDisabled={!!room || !!me?.branch}
          isRequired
          label="Филиал"
          options={branches.map((b) => ({ key: b.id, label: b.name }))}
          value={branchId}
          onChange={setBranchId}
        />
        <Input isRequired label="Название" value={name} onValueChange={setName} />
        <Input
          description="От 1 до 100"
          isRequired
          label="Вместимость"
          max={100}
          min={1}
          type="number"
          value={capacity}
          onValueChange={setCapacity}
        />
        {(error ?? edit.error) && (
          <p className="text-sm text-danger" role="alert">
            {error ?? edit.error}
          </p>
        )}
      </form>
      <ConflictDialog save={edit} />
    </AppModal>
  );
}

export function CourseFormModal({ course, onClose }: { course: Course | null; onClose: () => void }) {
  const refresh = useRefreshEducation();
  const [name, setName] = useState(course?.name ?? "");
  const [direction, setDirection] = useState(course?.direction ?? "");
  const [price, setPrice] = useState(course ? String(Number(course.default_price_month)) : "0");
  const [months, setMonths] = useState(String(course?.duration_months ?? 3));
  const [format, setFormat] = useState<string | null>(course?.format ?? "offline");
  const [error, setError] = useState<string | null>(null);
  const m = Number(months);
  const p = Number(price);
  const valid = name.trim() && format && Number.isInteger(m) && m >= 1 && m <= 36 && p >= 0;

  const values = {
    name: name.trim(),
    direction: direction.trim() || null,
    default_price_month: String(p),
    duration_months: m,
    format,
  };
  const done = () => {
    void refresh();
    notify(course ? "Курс сохранён" : "Курс добавлен");
    onClose();
  };
  const create = useMutation({
    mutationFn: () => api("/api/v1/courses", { method: "POST", body: values }),
    onSuccess: done,
    onError: (e) => setError(messageOf(e)),
  });
  const edit = useVersionedSave({
    record: course,
    values,
    toValues: (c) => ({
      name: c.name,
      direction: c.direction,
      default_price_month: String(Number(c.default_price_month)),
      duration_months: c.duration_months,
      format: c.format as string | null,
    }),
    apply: (v) => {
      setName(v.name);
      setDirection(v.direction ?? "");
      setPrice(v.default_price_month);
      setMonths(String(v.duration_months));
      setFormat(v.format);
    },
    request: (changed, version) =>
      api(`/api/v1/courses/${course?.id}`, { method: "PATCH", body: changed, version }),
    labels: {
      name: "Название",
      direction: "Направление",
      default_price_month: "Цена в месяц",
      duration_months: "Месяцев",
      format: "Формат",
    },
    show: { format: (f: string | null) => (f === "online" ? "Онлайн" : "Офлайн") },
    onSaved: done,
  });
  const submit = useSubmit(() => (course ? edit.save(values) : create.mutateAsync()), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <Button color="primary" isDisabled={!valid} isLoading={create.isPending || edit.pending} onPress={() => submit()}>
            {course ? "Сохранить" : "Добавить"}
          </Button>
        </>
      }
      isOpen
      size="md"
      title={course ? "Курс" : "Новый курс"}
      onClose={onClose}
    >
      <form
        className="space-y-4"
        onSubmit={submit}
      >
        <Input isRequired label="Название" value={name} onValueChange={setName} />
        <Input label="Направление" value={direction} onValueChange={setDirection} />
        <SelectField
          label="Формат"
          options={[
            { key: "offline", label: "Офлайн" },
            { key: "online", label: "Онлайн" },
          ]}
          value={format}
          onChange={setFormat}
        />
        <div className="grid grid-cols-2 gap-3">
          <Input
            endContent={<span className="text-xs text-default-500">TJS</span>}
            label="Цена в месяц"
            min={0}
            type="number"
            value={price}
            onValueChange={setPrice}
          />
          <Input label="Месяцев" max={36} min={1} type="number" value={months} onValueChange={setMonths} />
        </div>
        {(error ?? edit.error) && (
          <p className="text-sm text-danger" role="alert">
            {error ?? edit.error}
          </p>
        )}
      </form>
      <ConflictDialog save={edit} />
    </AppModal>
  );
}
