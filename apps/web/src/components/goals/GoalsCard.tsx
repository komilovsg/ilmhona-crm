"use client";

import { useState } from "react";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";

import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { EmptyState, QueryState } from "@/components/QueryState";
import { Bone } from "@/components/Skeletons";
import { useGoals, useNotes } from "@/hooks/goals";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { progressText, statusTone, type Goal } from "@/lib/goals";
import { notify, notifyError } from "@/lib/toast";
import { GoalFormModal } from "./GoalFormModal";

const BAR: Record<string, string> = {
  success: "bg-success",
  primary: "bg-primary",
  warning: "bg-warning",
  danger: "bg-danger",
};

function GoalNotes({ goalId }: { goalId: string }) {
  const notes = useNotes({ goal_id: goalId });

  return (
    <QueryState
      query={notes}
      skeleton={<Bone className="mt-2 h-12 w-full rounded-xl" />}
      isEmpty={(d) => d.items.length === 0}
      empty={<p className="mt-2 text-xs text-default-500">Заметок к цели нет</p>}
    >
      {(d) => (
        <ul className="mt-2 space-y-1.5">
          {d.items.map((n) => (
            <li key={n.id} className="rounded-xl bg-default-100 px-3 py-2 text-sm">
              <p className="whitespace-pre-wrap break-words">{n.text}</p>
              <p className="mt-0.5 text-xs text-default-500">{formatDate(n.created_at)}</p>
            </li>
          ))}
        </ul>
      )}
    </QueryState>
  );
}

function GoalRow({ goal, onEdit }: { goal: Goal; onEdit: (g: Goal) => void }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const tone = statusTone(goal.status);
  const toggle = useMutation({
    mutationFn: () => api<Goal>(`/api/v1/goals/${goal.id}/${goal.archived ? "unarchive" : "archive"}`, { method: "POST", version: goal.version }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["goals"] });
      notify(goal.archived ? "Цель возвращена из архива" : "Цель в архиве");
    },
    onError: notifyError,
  });

  return (
    <li className="rounded-xl border border-divider p-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="break-words text-sm font-medium">{goal.title}</h3>
          <p className="mt-0.5 text-xs text-default-500">
            до {formatDate(goal.deadline)} · {goal.branch_name ?? "все филиалы"}
          </p>
        </div>
        <Chip className="shrink-0" color={tone} size="sm" variant="flat">
          {goal.status}
        </Chip>
      </div>
      <div
        aria-label={`${goal.title}: выполнено ${goal.progress_pct}%`}
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={Math.round(goal.progress_pct)}
        className="relative mt-3 h-2.5 overflow-hidden rounded-full bg-default-200"
        role="progressbar"
      >
        <div className={clsx("h-full rounded-full", BAR[tone])} style={{ width: `${goal.progress_pct}%` }} />
        {goal.status !== "достигнута" && goal.expected_pct > 0 && goal.expected_pct < 100 && (
          <span aria-hidden className="absolute inset-y-0 w-0.5 bg-foreground/60" style={{ left: `${goal.expected_pct}%` }} title="Где нужно быть сегодня" />
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm tabular-nums">
          <span className="font-medium">{progressText(goal.current, goal.target, goal.metric)}</span>
          <span className="ml-2 text-xs text-default-500">{Math.round(goal.progress_pct)}%</span>
        </p>
        <div className="flex items-center gap-1">
          {goal.notes_count > 0 && (
            <Button aria-expanded={open} size="sm" startContent={<Icon name="message" size={14} />} variant="light" onPress={() => setOpen((o) => !o)}>
              Заметки {goal.notes_count}
            </Button>
          )}
          {!goal.archived && (
            <Button isIconOnly aria-label={`Изменить цель ${goal.title}`} size="sm" variant="light" onPress={() => onEdit(goal)}>
              <Icon name="edit" size={16} />
            </Button>
          )}
          <LoadingButton isLoading={toggle.isPending} size="sm" variant="light" onPress={() => toggle.mutate()}>
            {goal.archived ? "Вернуть" : "В архив"}
          </LoadingButton>
        </div>
      </div>
      {open && <GoalNotes goalId={goal.id} />}
    </li>
  );
}

/** «Цели» on the dashboard of the superadmin: progress comes from the server, nothing is typed in. */
export function GoalsCard() {
  const [archived, setArchived] = useState(false);
  const goals = useGoals(archived);
  const [form, setForm] = useState<{ goal?: Goal } | null>(null);

  return (
    <section aria-label="Цели" className="min-w-0 rounded-2xl bg-content1 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium">{archived ? "Цели в архиве" : "Цели"}</h2>
        <div className="flex items-center gap-1">
          <Button size="sm" variant="light" onPress={() => setArchived((a) => !a)}>
            {archived ? "К текущим" : "Архив"}
          </Button>
          <Button color="primary" size="sm" startContent={<Icon name="plus" size={16} />} onPress={() => setForm({})}>
            Цель
          </Button>
        </div>
      </div>
      <QueryState
        empty={
          <EmptyState
            title={archived ? "В архиве пусто" : "Целей пока нет"}
            hint={archived ? undefined : "Добавьте цель, например «500 активных студентов к сентябрю»: прогресс посчитается сам."}
          />
        }
        errorText="Не удалось загрузить цели"
        isEmpty={(d) => d.items.length === 0}
        query={goals}
        skeleton={
          <div className="space-y-3">
            {[0, 1].map((i) => (
              <Bone key={i} className="h-[7.5rem] w-full rounded-xl" />
            ))}
          </div>
        }
      >
        {(d) => (
          <ul className="grid gap-3 lg:grid-cols-2">
            {d.items.map((g) => (
              <GoalRow key={g.id} goal={g} onEdit={(goal) => setForm({ goal })} />
            ))}
          </ul>
        )}
      </QueryState>
      {form && <GoalFormModal goal={form.goal} onClose={() => setForm(null)} />}
    </section>
  );
}
