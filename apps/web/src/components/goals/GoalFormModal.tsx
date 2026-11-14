"use client";

import { useState } from "react";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { LoadingButton } from "@/components/LoadingButton";
import { SelectField } from "@/components/SelectField";
import { useBranches } from "@/hooks/queries";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import { GOAL_TITLE_MAX, METRICS, STOCK_METRICS, metricOf, validTarget, type Goal } from "@/lib/goals";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";

type Values = {
  title: string;
  metric: string;
  target: string;
  baseline: string;
  start_date: string;
  deadline: string;
  branch_id: string | null;
};

const plain = (n: number) => String(n);
const asNumber = (text: string) => Number(text.replace(",", ".").replace(/\s/g, ""));

function today(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dushanbe" }).format(new Date());
}

/** «+ Цель» and «Изменить цель». The numbers of a goal are computed by the server; here only the target is typed. */
export function GoalFormModal({ goal, onClose }: { goal?: Goal; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { data: branches = [] } = useBranches();
  const [title, setTitle] = useState(goal?.title ?? "");
  const [metric, setMetric] = useState(goal?.metric ?? METRICS[0].key);
  const [target, setTarget] = useState(goal ? plain(goal.target) : "");
  const [baseline, setBaseline] = useState(goal ? plain(goal.baseline) : "");
  const [start, setStart] = useState(goal?.start_date ?? today());
  const [deadline, setDeadline] = useState(goal?.deadline ?? "");
  const [branch, setBranch] = useState<string | null>(goal?.branch_id ?? null);
  const values: Values = { title: title.trim(), metric, target: target.trim(), baseline: STOCK_METRICS.includes(metric) ? baseline.trim() : "", start_date: start, deadline, branch_id: branch };
  const valid = values.title !== "" && validTarget(target, metric) && start !== "" && deadline > start;
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["goals"] });
  const body = (v: Partial<Values>) => ({
    ...v,
    ...(v.target !== undefined ? { target: asNumber(v.target) } : {}),
    // empty = «значение сейчас» (the server fills it in)
    ...(v.baseline !== undefined ? { baseline: v.baseline === "" ? null : asNumber(v.baseline) } : {}),
  });

  const create = useMutation({
    mutationFn: () => api<Goal>("/api/v1/goals", { method: "POST", body: body(values) }),
    onSuccess: () => {
      void refresh();
      notify("Цель добавлена");
      onClose();
    },
  });
  const save = useVersionedSave({
    record: goal ?? null,
    values,
    toValues: (r: Goal): Values => ({
      title: r.title,
      metric: r.metric,
      target: plain(r.target),
      baseline: STOCK_METRICS.includes(r.metric) ? plain(r.baseline) : "",
      start_date: r.start_date,
      deadline: r.deadline,
      branch_id: r.branch_id,
    }),
    apply: (v) => {
      setTitle(v.title);
      setMetric(v.metric);
      setTarget(v.target);
      setBaseline(v.baseline);
      setStart(v.start_date);
      setDeadline(v.deadline);
      setBranch(v.branch_id);
    },
    request: (changed, version) => api<Goal>(`/api/v1/goals/${goal?.id}`, { method: "PATCH", body: body(changed), version }),
    labels: { title: "Название", metric: "Показатель", target: "План", baseline: "Старт", start_date: "Начало", deadline: "Срок", branch_id: "Филиал" },
    show: { metric: (m: string) => metricOf(m).label, branch_id: (b: string | null) => branches.find((x) => x.id === b)?.name ?? "Все филиалы" },
    onSaved: () => {
      void refresh();
      notify("Цель сохранена");
      onClose();
    },
  });
  const fe = useFieldErrors(goal ? save.failure : create.error, ["title", "metric", "target", "start_date", "deadline", "branch_id"]);
  const submit = useSubmit(() => (goal ? save.save(values) : create.mutateAsync()), !valid);
  const unit = metricOf(metric).unit;

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={create.isPending || save.pending} onPress={() => submit()}>
            {goal ? "Сохранить" : "Добавить"}
          </LoadingButton>
        </>
      }
      isOpen
      title={goal ? "Изменить цель" : "Новая цель"}
      onClose={onClose}
    >
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit}>
        <Input
          autoFocus
          isRequired
          className="sm:col-span-2"
          label="Название"
          maxLength={GOAL_TITLE_MAX}
          placeholder="Например: 1 000 выпускников к лету 2027"
          value={title}
          {...fe.field("title", setTitle)}
        />
        <div className="sm:col-span-2">
          <SelectField
            isRequired
            label="Показатель"
            options={METRICS.map((m) => ({ key: m.key, label: m.label }))}
            value={metric}
            onChange={(m) => m && setMetric(m)}
          />
          <p className="mt-1.5 px-1 text-xs text-default-500">{metricOf(metric).hint}</p>
        </div>
        <Input
          isRequired
          endContent={unit ? <span className="text-xs text-default-500">{unit}</span> : undefined}
          inputMode="decimal"
          isInvalid={(target !== "" && !validTarget(target, metric)) || fe.hint("target").isInvalid}
          errorMessage={fe.hint("target").errorMessage ?? (metric === "collection_rate_month" ? "От 1 до 100" : "Больше нуля")}
          label="План"
          validationBehavior="aria"
          value={target}
          onValueChange={(v) => {
            fe.clear("target");
            setTarget(v);
          }}
        />
        {STOCK_METRICS.includes(metric) && (
          <Input
            description="Сколько было в начале. Пусто — возьмём значение на момент сохранения."
            inputMode="decimal"
            label="Старт"
            value={baseline}
            onValueChange={setBaseline}
          />
        )}
        <SelectField
          allLabel="Все филиалы"
          label="Филиал"
          options={branches.map((b) => ({ key: b.id, label: b.name }))}
          value={branch}
          onChange={setBranch}
        />
        <Input isRequired label="Начало" placeholder=" " type="date" value={start} {...fe.field("start_date", setStart)} />
        <Input
          isRequired
          errorMessage={fe.hint("deadline").errorMessage ?? "Срок должен быть позже начала"}
          isInvalid={(deadline !== "" && deadline <= start) || fe.hint("deadline").isInvalid}
          label="Срок"
          validationBehavior="aria"
          placeholder=" "
          type="date"
          value={deadline}
          onValueChange={(v) => {
            fe.clear("deadline");
            setDeadline(v);
          }}
        />
        {fe.message && (
          <p className="text-sm text-danger sm:col-span-2" role="alert">
            {fe.message}
          </p>
        )}
      </form>
      <ConflictDialog save={save} />
    </AppModal>
  );
}
