"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { LoadingButton } from "@/components/LoadingButton";
import { SelectField } from "@/components/SelectField";
import { useCourses } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { useRefreshSales } from "@/hooks/sales";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api, messageOf } from "@/lib/api";
import { MAX_DATE, MIN_DATE } from "@/lib/education";
import { amountText, validRate } from "@/lib/money";
import { CAMPAIGN_STATUSES, PLATFORMS } from "@/lib/sales";
import type { CampaignRow } from "@/lib/sales-types";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";

type Values = {
  name: string;
  course_id: string | null;
  platform: string;
  start_date: string;
  end_date: string | null;
  budget: string;
  status: string;
};

export function CampaignFormModal({ campaign, onClose }: { campaign: CampaignRow | null; onClose: () => void }) {
  const refresh = useRefreshSales();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const { data: courses = [] } = useCourses();
  const [name, setName] = useState(campaign?.name ?? "");
  const [courseId, setCourseId] = useState<string | null>(campaign?.course_id ?? null);
  const [branchId, setBranchId] = useState<string | null>(campaign?.branch_id ?? me?.branch?.id ?? null);
  const [platform, setPlatform] = useState(campaign?.platform ?? "Facebook Ads");
  const [start, setStart] = useState(campaign?.start_date ?? "");
  const [end, setEnd] = useState(campaign?.end_date ?? "");
  const [budget, setBudget] = useState(campaign ? String(Number(campaign.budget)) : "0");
  const [status, setStatus] = useState(campaign?.status ?? "запланирована");
  const [error, setError] = useState<string | null>(null);

  const budgetOk = validRate(budget);
  const datesOk = !end || !start || end >= start;
  const valid = name.trim() && start && budgetOk && datesOk && (campaign || branchId);
  const values: Values = {
    name: name.trim(),
    course_id: courseId,
    platform,
    start_date: start,
    end_date: end || null,
    budget: amountText(budget),
    status,
  };
  const done = () => {
    void refresh();
    notify(campaign ? "Кампания сохранена" : "Кампания добавлена");
    onClose();
  };
  const create = useMutation({
    mutationFn: () => api("/api/v1/campaigns", { method: "POST", body: { ...values, branch_id: branchId } }),
    onSuccess: done,
    onError: (e) => setError(messageOf(e)),
  });
  const edit = useVersionedSave({
    record: campaign,
    values,
    toValues: (c): Values => ({
      name: c.name,
      course_id: c.course_id,
      platform: c.platform,
      start_date: c.start_date,
      end_date: c.end_date,
      budget: String(Number(c.budget)),
      status: c.status,
    }),
    apply: (v) => {
      setName(v.name);
      setCourseId(v.course_id);
      setPlatform(v.platform);
      setStart(v.start_date);
      setEnd(v.end_date ?? "");
      setBudget(v.budget);
      setStatus(v.status);
    },
    request: (changed, version) => api(`/api/v1/campaigns/${campaign?.id}`, { method: "PATCH", body: changed, version }),
    labels: {
      name: "Название",
      course_id: "Курс",
      platform: "Платформа",
      start_date: "Старт",
      end_date: "Окончание",
      budget: "Бюджет",
      status: "Статус",
    },
    onSaved: done,
  });
  const pending = create.isPending || edit.pending;
  const submit = useSubmit(() => (campaign ? edit.save(values) : create.mutateAsync()), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={pending} onPress={() => submit()}>
            {campaign ? "Сохранить" : "Добавить"}
          </LoadingButton>
        </>
      }
      isOpen
      size="lg"
      title={campaign ? "Кампания" : "Новая кампания"}
      onClose={onClose}
    >
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit}>
        <Input className="sm:col-span-2" isRequired label="Название" value={name} onValueChange={setName} />
        <SelectField
          label="Платформа"
          options={PLATFORMS.map((p) => ({ key: p, label: p }))}
          value={platform}
          onChange={(p) => setPlatform(p ?? "другое")}
        />
        <SelectField
          allLabel="Без курса"
          label="Курс"
          options={courses.map((c) => ({ key: c.id, label: c.name }))}
          value={courseId}
          onChange={setCourseId}
        />
        <SelectField
          isDisabled={!!campaign || !!me?.branch}
          isRequired
          label="Филиал"
          options={branches.map((b) => ({ key: b.id, label: b.name }))}
          value={branchId}
          onChange={setBranchId}
        />
        <SelectField
          label="Статус"
          options={CAMPAIGN_STATUSES.map((s) => ({ key: s, label: s }))}
          value={status}
          onChange={(s) => setStatus(s ?? "запланирована")}
        />
        <Input isRequired label="Старт" max={MAX_DATE} min={MIN_DATE} type="date" value={start} onValueChange={setStart} />
        <Input
          errorMessage="Раньше даты старта"
          isInvalid={!datesOk}
          label="Окончание"
          max={MAX_DATE}
          min={start || MIN_DATE}
          type="date"
          value={end}
          onValueChange={setEnd}
        />
        <Input
          className="sm:col-span-2"
          endContent={<span className="text-sm text-default-500">TJS</span>}
          errorMessage="Сумма от 0, не больше двух знаков после запятой"
          inputMode="decimal"
          isInvalid={!budgetOk}
          isRequired
          label="Бюджет"
          value={budget}
          onValueChange={setBudget}
        />
        {(error ?? edit.error) && (
          <p className="text-sm text-danger sm:col-span-2" role="alert">
            {error ?? edit.error}
          </p>
        )}
      </form>
      <ConflictDialog save={edit} />
    </AppModal>
  );
}
