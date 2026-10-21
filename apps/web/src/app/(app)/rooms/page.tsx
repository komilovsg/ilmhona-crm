"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";

import { CourseFormModal, RoomFormModal } from "./forms";
import { ScheduleTab } from "./ScheduleTab";

import { ConfirmModal } from "@/components/ConfirmModal";
import { Icon } from "@/components/Icon";
import { ExportButton } from "@/components/ExportButton";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, QueryState } from "@/components/QueryState";
import { ListSkeleton } from "@/components/Skeletons";
import { RowMenu } from "@/components/RowMenu";
import { Segmented } from "@/components/Segmented";
import { useMe } from "@/hooks/queries";
import { useCanChange, useCourses, useRefreshEducation, useRooms } from "@/hooks/education";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/education";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";
import type { Course, Room } from "@/lib/types";

type Tab = "schedule" | "rooms" | "courses";
type Removal = { kind: "room"; item: Room } | { kind: "course"; item: Course };

const ACTIONS = [
  { key: "edit", label: "Изменить", icon: "edit" },
  { key: "delete", label: "Удалить", icon: "trash", danger: true },
];

function RoomsList({ canChange, onEdit, onDelete }: { canChange: boolean; onEdit: (r: Room) => void; onDelete: (r: Room) => void }) {
  const rooms = useRooms();

  if (rooms.data === undefined || rooms.data.length === 0)
    return (
      <QueryState
        empty={<EmptyState hint={canChange ? "Добавьте первую кнопкой «Аудитория» сверху." : undefined} title="Нет аудиторий" />}
        isEmpty={(d) => d.length === 0}
        query={rooms}
        skeleton={<ListSkeleton cols={4} />}
      >
        {null}
      </QueryState>
    );

  const menu = (r: Room) =>
    canChange && (
      <RowMenu
        actions={ACTIONS}
        label={`Действия: ${r.name}`}
        onAction={(k) => (k === "edit" ? onEdit(r) : onDelete(r))}
      />
    );

  return (
    <>
      <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-divider text-xs text-default-500">
            <tr>
              <th className="px-4 py-3 font-medium">Название</th>
              <th className="px-4 py-3 font-medium">Филиал</th>
              <th className="px-4 py-3 font-medium">Вместимость</th>
              <th className="w-12" />
            </tr>
          </thead>
          <tbody>
            {rooms.data.map((r) => (
              <tr key={r.id} className="border-b border-divider last:border-0 hover:bg-default-50">
                <td className="px-4 py-3 font-medium">{r.name}</td>
                <td className="px-4 py-3">{r.branch_name}</td>
                <td className="px-4 py-3">{r.capacity}</td>
                <td className="px-2">{menu(r)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul data-rows className="space-y-3 md:hidden">
        {rooms.data.map((r) => (
          <li key={r.id} className="flex items-start justify-between gap-2 rounded-2xl bg-content1 p-4">
            <div>
              <div className="font-medium">{r.name}</div>
              <div className="text-sm text-default-500">
                {r.branch_name} · {r.capacity} мест
              </div>
            </div>
            {menu(r)}
          </li>
        ))}
      </ul>
    </>
  );
}

function CoursesList({ canChange, onEdit, onDelete }: { canChange: boolean; onEdit: (c: Course) => void; onDelete: (c: Course) => void }) {
  const courses = useCourses();

  if (courses.data === undefined || courses.data.length === 0)
    return (
      <QueryState
        empty={<EmptyState hint={canChange ? "Добавьте первый кнопкой «Курс» сверху." : undefined} title="Нет курсов" />}
        isEmpty={(d) => d.length === 0}
        query={courses}
        skeleton={<ListSkeleton cols={6} />}
      >
        {null}
      </QueryState>
    );

  const menu = (c: Course) =>
    canChange && (
      <RowMenu
        actions={ACTIONS}
        label={`Действия: ${c.name}`}
        onAction={(k) => (k === "edit" ? onEdit(c) : onDelete(c))}
      />
    );
  const format = (c: Course) => (c.format === "online" ? "Онлайн" : "Офлайн");

  return (
    <>
      <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-divider text-xs text-default-500">
            <tr>
              <th className="px-4 py-3 font-medium">Курс</th>
              <th className="px-4 py-3 font-medium">Направление</th>
              <th className="px-4 py-3 font-medium">Формат</th>
              <th className="px-4 py-3 font-medium">Месяцев</th>
              <th className="px-4 py-3 font-medium">Цена в месяц</th>
              <th className="w-12" />
            </tr>
          </thead>
          <tbody>
            {courses.data.map((c) => (
              <tr key={c.id} className="border-b border-divider last:border-0 hover:bg-default-50">
                <td className="px-4 py-3 font-medium">{c.name}</td>
                <td className="px-4 py-3">{c.direction ?? "—"}</td>
                <td className="px-4 py-3">{format(c)}</td>
                <td className="px-4 py-3">{c.duration_months}</td>
                <td className="px-4 py-3 tabular-nums">{formatPrice(c.default_price_month)}</td>
                <td className="px-2">{menu(c)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul data-rows className="space-y-3 md:hidden">
        {courses.data.map((c) => (
          <li key={c.id} className="flex items-start justify-between gap-2 rounded-2xl bg-content1 p-4">
            <div className="min-w-0">
              <div className="font-medium">{c.name}</div>
              <div className="text-sm text-default-500">
                {[c.direction, format(c), `${c.duration_months} мес.`].filter(Boolean).join(" · ")}
              </div>
              <div className="mt-1 text-sm tabular-nums">{formatPrice(c.default_price_month)} в месяц</div>
            </div>
            {menu(c)}
          </li>
        ))}
      </ul>
    </>
  );
}

export default function RoomsPage() {
  const refresh = useRefreshEducation();
  const canChange = useCanChange("rooms");
  const { data: me } = useMe();
  // courses are shared by both branches: only users without a branch write them (the API says 403)
  const canChangeCourses = canChange && !me?.branch;
  const [tab, setTab] = useState<Tab>("schedule");
  const [roomForm, setRoomForm] = useState<Room | "new" | null>(null);
  const [courseForm, setCourseForm] = useState<Course | "new" | null>(null);
  const [removal, setRemoval] = useState<Removal | null>(null);

  const remove = useMutation({
    mutationFn: ({ kind, item }: Removal) => api(`/api/v1/${kind === "room" ? "rooms" : "courses"}/${item.id}`, { method: "DELETE" }),
    onSuccess: () => {
      void refresh();
      notify("Удалено");
      setRemoval(null);
    },
    onError: (e) => {
      setRemoval(null);
      notifyError(e);
    },
  });
  const confirm = useSubmit(() => removal ? remove.mutateAsync(removal) : Promise.resolve());

  return (
    <>
      <PageHeader
        actions={
          <>
            {tab === "rooms" && <ExportButton path="/api/v1/rooms/export" />}
            {tab === "courses" && <ExportButton path="/api/v1/courses/export" />}
            {(tab === "courses" ? canChangeCourses : canChange) && tab !== "schedule" && (
              <Button
                color="primary"
                startContent={<Icon name="plus" size={18} />}
                onPress={() => (tab === "rooms" ? setRoomForm("new") : setCourseForm("new"))}
              >
                {tab === "rooms" ? "Аудитория" : "Курс"}
              </Button>
            )}
          </>
        }
        title="Аудитории"
      />
      <Segmented
        className="mb-4"
        label="Раздел"
        options={[
          { key: "schedule", label: "Расписание" },
          { key: "rooms", label: "Аудитории" },
          { key: "courses", label: "Курсы" },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "schedule" && <ScheduleTab />}
      {tab === "rooms" && (
        <RoomsList canChange={canChange} onDelete={(item) => setRemoval({ kind: "room", item })} onEdit={setRoomForm} />
      )}
      {tab === "courses" && (
        <CoursesList canChange={canChangeCourses} onDelete={(item) => setRemoval({ kind: "course", item })} onEdit={setCourseForm} />
      )}

      {roomForm && <RoomFormModal room={roomForm === "new" ? null : roomForm} onClose={() => setRoomForm(null)} />}
      {courseForm && (
        <CourseFormModal course={courseForm === "new" ? null : courseForm} onClose={() => setCourseForm(null)} />
      )}
      {removal && (
        <ConfirmModal
          confirmLabel="Удалить"
          danger
          isLoading={remove.isPending}
          isOpen
          title={removal.kind === "room" ? "Удалить аудиторию" : "Удалить курс"}
          onClose={() => setRemoval(null)}
          onConfirm={() => confirm()}
        >
          Будет удалено: «{removal.item.name}». Если с этим связаны потоки, система не даст это сделать.
        </ConfirmModal>
      )}
    </>
  );
}
