"use client";

import { useState } from "react";
import { Button } from "@heroui/button";
import { Textarea } from "@heroui/input";
import { useQueryClient } from "@tanstack/react-query";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { Bone, Late } from "@/components/Skeletons";
import { ACADEMY_GOAL_KEY, useAcademyGoal, useIsSuperadmin } from "@/hooks/goals";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import { charsLeft, GOAL_TEXT_MAX, type AcademyGoal } from "@/lib/goals";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";

function EditModal({ goal, onClose }: { goal: AcademyGoal; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [text, setText] = useState(goal.text);
  const values = { text: text.trim() };

  const save = useVersionedSave({
    record: goal,
    values,
    toValues: (r: AcademyGoal) => ({ text: r.text }),
    apply: (v) => setText(v.text),
    request: (changed, version) => api<AcademyGoal>("/api/v1/academy/goal", { method: "PATCH", body: changed, version }),
    labels: { text: "Цель академии" },
    show: { text: (t: string) => (t ? `«${t}»` : "пусто") },
    onSaved: (result) => {
      if (result) queryClient.setQueryData(ACADEMY_GOAL_KEY, result);
      notify("Цель академии сохранена");
      onClose();
    },
  });
  const fe = useFieldErrors(save.failure, ["text"]);
  const submit = useSubmit(() => save.save(values));

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isLoading={save.pending} onPress={() => submit()}>
            Сохранить
          </LoadingButton>
        </>
      }
      isOpen
      size="md"
      title="Цель академии"
      onClose={onClose}
    >
      <form className="space-y-3" onSubmit={submit}>
        <Textarea
          autoFocus
          description={`Осталось ${charsLeft(text, GOAL_TEXT_MAX)} из ${GOAL_TEXT_MAX} знаков`}
          label="Одна фраза для всей команды"
          maxLength={GOAL_TEXT_MAX}
          minRows={3}
          placeholder="К лету 2027 — 1 000 выпускников с работой в IT и креативе"
          value={text}
          {...fe.field("text", setText)}
        />
        <p className="text-sm text-default-500">Её видят все сотрудники сверху на дашборде и на странице «Сегодня». Пустой текст убирает цель.</p>
        {fe.message && (
          <p className="text-sm text-danger" role="alert">
            {fe.message}
          </p>
        )}
      </form>
      <ConflictDialog save={save} />
    </AppModal>
  );
}

/**
 * The academy's north star: one line on top of the dashboard and «Сегодня» for every role. Hidden when
 * empty (the superadmin gets a «Задать цель академии» button instead).
 */
export function AcademyGoalBanner() {
  const query = useAcademyGoal();
  const isSuperadmin = useIsSuperadmin();
  const [editing, setEditing] = useState(false);

  if (query.isPending)
    return (
      <Late>
        <Bone className="mb-4 h-14 w-full rounded-2xl" />
      </Late>
    );
  if (!query.data) return null;

  const { text } = query.data;

  if (!text && !isSuperadmin) return null;

  return (
    <section aria-label="Цель академии" className="mb-4 flex min-h-14 items-center gap-3 rounded-2xl bg-primary/10 px-4 py-2.5">
      <Icon className="shrink-0 text-brand-text" name="graduates" size={22} />
      <p className="min-w-0 flex-1 text-sm leading-snug">
        {text ? (
          <>
            <span className="font-medium">Цель академии: </span>«{text}»
          </>
        ) : (
          <span className="text-default-600">Цель академии не задана</span>
        )}
      </p>
      {isSuperadmin && (
        <Button size="sm" startContent={<Icon name="edit" size={16} />} variant="flat" onPress={() => setEditing(true)}>
          {text ? "Изменить" : "Задать цель академии"}
        </Button>
      )}
      {editing && <EditModal goal={query.data} onClose={() => setEditing(false)} />}
    </section>
  );
}
