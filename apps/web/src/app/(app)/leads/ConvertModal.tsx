"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";

import { AppModal } from "@/components/AppModal";
import { LoadingButton } from "@/components/LoadingButton";
import { QueryState } from "@/components/QueryState";
import { SelectField } from "@/components/SelectField";
import { useCanChange, useRefreshEducation } from "@/hooks/education";
import { useCanPay } from "@/hooks/money";
import { useRefreshSales } from "@/hooks/sales";
import { api, messageOf } from "@/lib/api";
import { formatPrice, fullDate } from "@/lib/education";
import type { ConvertResult, LeadRow } from "@/lib/sales-types";
import { Bone } from "@/components/Skeletons";
import { OverCapacityNotice } from "@/components/OverCapacityNotice";
import { overToast, wouldExceed } from "@/lib/capacity";
import { convertCohorts } from "@/lib/convert-cohort";
import { lazyModal } from "@/lib/lazy-modal";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";
import type { CohortRow, Paged } from "@/lib/types";

const PaymentFormModal = lazyModal(() => import("../payments/PaymentFormModal").then((m) => m.PaymentFormModal));

/**
 * «Записать в поток»: one action turns the lead into a student (linked by phone when the branch
 * already has one) and, if a cohort is picked, enrolls them. Safe to repeat: same student back.
 */
export function ConvertModal({ lead, onClose }: { lead: LeadRow; onClose: () => void }) {
  const refreshSales = useRefreshSales();
  const refreshEducation = useRefreshEducation();
  const canEnroll = useCanChange("cohorts");
  const canPay = useCanPay();
  // undefined: the user has not chosen yet, the lead's own course decides
  const [picked, setPicked] = useState<string | null | undefined>(undefined);
  const [paying, setPaying] = useState(false);
  const [result, setResult] = useState<ConvertResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cohorts = useQuery({
    queryKey: ["cohorts", "convert", lead.branch_id],
    queryFn: () => api<Paged<CohortRow>>("/api/v1/cohorts", { params: { branch_id: lead.branch_id, page_size: "100" } }),
    enabled: canEnroll,
  });
  const { items: open, match, auto } = convertCohorts(cohorts.data?.items ?? [], lead.course_id);
  const cohortId = picked === undefined ? auto : picked;
  const chosen = open.find((c) => c.id === cohortId);
  const exceeds = wouldExceed(chosen?.fill);

  const convert = useMutation({
    mutationFn: () =>
      api<ConvertResult>(`/api/v1/leads/${lead.id}/convert`, { method: "POST", body: { cohort_id: cohortId } }),
    onSuccess: (r) => {
      void refreshSales();
      void refreshEducation();
      if (r.enrollment?.over_capacity) notify(`Записан${overToast(r.enrollment.over_capacity)}`);
      setResult(r);
    },
    onError: (e) => setError(messageOf(e)),
  });
  const submit = useSubmit(() => convert.mutateAsync());

  if (result && paying && result.enrollment)
    return <PaymentFormModal enrollmentId={result.enrollment.id} payment={null} onClose={onClose} />;

  const canPayNow = !!result?.enrollment && canPay;

  if (result)
    return (
      <AppModal
        footer={
          <>
            <Button color={canPayNow ? "default" : "primary"} variant={canPayNow ? "light" : "solid"} onPress={onClose}>
              Готово
            </Button>
            {canPayNow && (
              <Button color="primary" onPress={() => setPaying(true)}>
                Внести оплату
              </Button>
            )}
          </>
        }
        isOpen
        size="md"
        title={result.already ? "Лид уже был записан" : "Лид записан"}
        onClose={onClose}
      >
        <div className="space-y-2 text-sm">
          <p>
            {result.student.created ? "Создан студент" : "Привязан существующий студент (тот же телефон)"}:{" "}
            <Link className="font-medium text-brand-text" href={`/students/${result.student.id}`}>
              {result.student.full_name}
            </Link>
          </p>
          {result.enrollment && (
            <p>
              {result.enrollment.new ? "Зачислен в поток" : "Уже в потоке"}{" "}
              <Link className="font-medium text-brand-text" href={`/cohorts/${result.enrollment.cohort_id}`}>
                {result.enrollment.cohort_code}
              </Link>
            </p>
          )}
        </div>
      </AppModal>
    );

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isLoading={convert.isPending} onPress={() => submit()}>
            {cohortId ? (exceeds ? "Записать всё равно" : "Записать в поток") : "Создать студента"}
          </LoadingButton>
        </>
      }
      isOpen
      size="md"
      title="Записать в поток"
      onClose={onClose}
    >
      <div className="space-y-4">
        <div className="rounded-xl bg-content2 p-3 text-sm">
          <div className="font-medium">{lead.full_name}</div>
          <div className="text-default-500">
            {lead.phone ?? "без телефона"} · {lead.branch_name}
          </div>
        </div>
        {lead.status === "записан" && (
          <p className="text-sm text-default-600">Лид уже студент. Можно записать его в ещё один поток.</p>
        )}
        {canEnroll ? (
          <QueryState query={cohorts} skeleton={<Bone className="h-14 w-full rounded-xl" />}>
            <SelectField
              allLabel="Только создать студента, без потока"
              label="Поток"
              options={open.map((c) => ({
                key: c.id,
                label: `${match.has(c.id) ? "по курсу лида · " : ""}${c.code} · ${c.course_name} · с ${fullDate(c.start_date)} · ${formatPrice(c.price_month)}/мес · ${c.fill.enrolled >= c.capacity ? `сверх плана (${c.fill.enrolled} из ${c.capacity})` : `мест: ${c.capacity - c.fill.enrolled}`}`,
              }))}
              value={cohortId}
              onChange={setPicked}
            />
          </QueryState>
        ) : (
          <p className="text-sm text-default-500">Запись в поток доступна с правом «Потоки: изменение».</p>
        )}
        <OverCapacityNotice fill={chosen?.fill} />
        {error && (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </div>
    </AppModal>
  );
}
