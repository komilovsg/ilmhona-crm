"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { SelectField } from "@/components/SelectField";
import { useRefreshEducation } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { api, messageOf } from "@/lib/api";
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

  const save = useMutation({
    mutationFn: () =>
      room
        ? api(`/api/v1/rooms/${room.id}`, { method: "PATCH", body: { name, capacity: size } })
        : api("/api/v1/rooms", { method: "POST", body: { name, capacity: size, branch_id: branchId } }),
    onSuccess: () => {
      void refresh();
      notify(room ? "Аудитория сохранена" : "Аудитория добавлена");
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
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) save.mutate();
        }}
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
        {error && (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </form>
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

  const save = useMutation({
    mutationFn: () => {
      const body = {
        name,
        direction: direction.trim() || null,
        default_price_month: String(p),
        duration_months: m,
        format,
      };

      return course
        ? api(`/api/v1/courses/${course.id}`, { method: "PUT", body })
        : api("/api/v1/courses", { method: "POST", body });
    },
    onSuccess: () => {
      void refresh();
      notify(course ? "Курс сохранён" : "Курс добавлен");
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
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) save.mutate();
        }}
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
        {error && (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </form>
    </AppModal>
  );
}
