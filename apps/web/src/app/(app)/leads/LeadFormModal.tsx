"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input, Textarea } from "@heroui/input";
import { Switch } from "@heroui/switch";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { LoadingButton } from "@/components/LoadingButton";
import { SelectField } from "@/components/SelectField";
import { useCourses } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { useRefreshSales } from "@/hooks/sales";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api, messageOf } from "@/lib/api";
import { CALL_STATUSES, fromLocalInput, LEAD_SOURCES, localInput } from "@/lib/sales";
import type { CampaignList, LeadRow } from "@/lib/sales-types";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";

const OPEN_STATUSES = ["новый", "заинтересован", "нулевой урок", "отказ"] as const;

type Values = {
  full_name: string;
  phone: string | null;
  course_id: string | null;
  source: string;
  campaign_id: string | null;
  call_status: string;
  next_contact_at: string | null;
  status: string;
  refusal_reason: string | null;
  comment: string | null;
  needs_review: boolean;
};

function valuesOf(l: LeadRow): Values {
  return {
    full_name: l.full_name,
    phone: l.phone_raw ?? l.phone,
    course_id: l.course_id,
    source: l.source,
    campaign_id: l.campaign_id,
    call_status: l.call_status,
    next_contact_at: l.next_contact_at,
    status: l.status,
    refusal_reason: l.refusal_reason,
    comment: l.comment,
    needs_review: l.needs_review,
  };
}

/** Create or edit a lead. `onSaved` gets the saved lead (it may carry a duplicate-phone warning). */
export function LeadFormModal({
  lead,
  onClose,
  onSaved,
}: {
  lead: LeadRow | null;
  onClose: () => void;
  onSaved: (lead: LeadRow) => void;
}) {
  const refresh = useRefreshSales();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const { data: courses = [] } = useCourses();
  const [name, setName] = useState(lead?.full_name ?? "");
  const [phone, setPhone] = useState(lead ? (lead.phone_raw ?? lead.phone ?? "") : "");
  const [courseId, setCourseId] = useState<string | null>(lead?.course_id ?? null);
  const [source, setSource] = useState(lead?.source ?? "другое");
  const [campaignId, setCampaignId] = useState<string | null>(lead?.campaign_id ?? null);
  const [branchId, setBranchId] = useState<string | null>(lead?.branch_id ?? me?.branch?.id ?? null);
  const [callStatus, setCallStatus] = useState(lead?.call_status ?? "не звонили");
  const [nextContact, setNextContact] = useState(localInput(lead?.next_contact_at));
  const [status, setStatus] = useState(lead?.status ?? "новый");
  const [reason, setReason] = useState(lead?.refusal_reason ?? "");
  const [comment, setComment] = useState(lead?.comment ?? "");
  const [needsReview, setNeedsReview] = useState(lead?.needs_review ?? false);
  const [error, setError] = useState<string | null>(null);
  const converted = lead?.status === "записан";
  const valid = name.trim() && (lead || branchId);

  const campaigns = useQuery({
    queryKey: ["campaigns", "options", branchId],
    queryFn: () => api<CampaignList>("/api/v1/campaigns", { params: { branch_id: branchId ?? undefined } }),
    enabled: !!branchId,
    retry: false,
  });

  const values: Values = {
    full_name: name.trim(),
    phone: phone.trim() || null,
    course_id: courseId,
    source,
    campaign_id: campaignId,
    call_status: callStatus,
    // an untouched time stays exactly as the server sent it (no phantom change)
    next_contact_at: nextContact === localInput(lead?.next_contact_at) ? (lead?.next_contact_at ?? null) : fromLocalInput(nextContact),
    status,
    refusal_reason: status === "отказ" ? reason.trim() || null : null,
    comment: comment.trim() || null,
    needs_review: needsReview,
  };
  const done = (saved: unknown) => {
    void refresh();
    notify(lead ? "Лид сохранён" : "Лид добавлен");
    onSaved(saved as LeadRow);
  };
  const create = useMutation({
    mutationFn: () => {
      const body = Object.fromEntries(Object.entries(values).filter(([k]) => k !== "needs_review"));

      return api<LeadRow>("/api/v1/leads", { method: "POST", body: { ...body, branch_id: branchId } });
    },
    onSuccess: done,
    onError: (e) => setError(messageOf(e)),
  });
  const edit = useVersionedSave({
    record: lead,
    values,
    toValues: valuesOf,
    apply: (v) => {
      setName(v.full_name);
      setPhone(v.phone ?? "");
      setCourseId(v.course_id);
      setSource(v.source);
      setCampaignId(v.campaign_id);
      setCallStatus(v.call_status);
      setNextContact(localInput(v.next_contact_at));
      setStatus(v.status);
      setReason(v.refusal_reason ?? "");
      setComment(v.comment ?? "");
      setNeedsReview(v.needs_review);
    },
    request: (changed, version) => api(`/api/v1/leads/${lead?.id}`, { method: "PATCH", body: changed, version }),
    labels: {
      full_name: "ФИО",
      phone: "Телефон",
      course_id: "Курс",
      source: "Источник",
      campaign_id: "Кампания",
      call_status: "Статус звонка",
      next_contact_at: "Перезвонить",
      status: "Статус",
      refusal_reason: "Причина отказа",
      comment: "Комментарий",
      needs_review: "Нужна проверка",
    },
    onSaved: done,
  });
  const pending = create.isPending || edit.pending;
  const submit = useSubmit(() => (lead ? edit.save(values) : create.mutateAsync()), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={pending} onPress={() => submit()}>
            {lead ? "Сохранить" : "Добавить"}
          </LoadingButton>
        </>
      }
      isOpen
      size="lg"
      title={lead ? "Лид" : "Новый лид"}
      onClose={onClose}
    >
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit}>
        <Input
          className="sm:col-span-2"
          description={
            lead?.raw_name && lead.raw_name !== lead.full_name ? `Пришло из формы: ${lead.raw_name}` : undefined
          }
          isRequired
          label="ФИО"
          value={name}
          onValueChange={setName}
        />
        <Input label="Телефон" type="tel" value={phone} onValueChange={setPhone} />
        <SelectField
          allLabel="Не указан"
          label="Курс"
          options={courses.map((c) => ({ key: c.id, label: c.name }))}
          value={courseId}
          onChange={setCourseId}
        />
        <SelectField
          label="Источник"
          options={LEAD_SOURCES.map((s) => ({ key: s, label: s }))}
          value={source}
          onChange={(v) => setSource(v ?? "другое")}
        />
        <SelectField
          allLabel="Без кампании"
          isDisabled={!branchId}
          label="Кампания"
          options={(campaigns.data?.items ?? []).map((c) => ({ key: c.id, label: c.name }))}
          value={campaignId}
          onChange={setCampaignId}
        />
        <SelectField
          isDisabled={!!lead || !!me?.branch}
          isRequired
          label="Филиал"
          options={branches.map((b) => ({ key: b.id, label: b.name }))}
          value={branchId}
          onChange={(b) => {
            setBranchId(b);
            setCampaignId(null);
          }}
        />
        <SelectField
          label="Статус"
          isDisabled={converted}
          options={(converted ? ["записан"] : OPEN_STATUSES).map((s) => ({ key: s, label: s }))}
          value={status}
          onChange={(v) => setStatus(v ?? "новый")}
        />
        {status === "отказ" && (
          <Input label="Причина отказа" value={reason} onValueChange={setReason} />
        )}
        <SelectField
          label="Звонок"
          options={CALL_STATUSES.map((s) => ({ key: s, label: s }))}
          value={callStatus}
          onChange={(v) => setCallStatus(v ?? "не звонили")}
        />
        <Input
          description={callStatus === "перезвонить" ? "Пусто — сейчас: лид попадёт в «Перезвонить сегодня»." : undefined}
          label="Когда перезвонить"
          type="datetime-local"
          value={nextContact}
          onValueChange={setNextContact}
        />
        <Textarea className="sm:col-span-2" label="Комментарий" minRows={2} value={comment} onValueChange={setComment} />
        {lead?.needs_review && (
          <Switch className="sm:col-span-2" isSelected={needsReview} onValueChange={setNeedsReview}>
            Нужна проверка имени
          </Switch>
        )}
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
