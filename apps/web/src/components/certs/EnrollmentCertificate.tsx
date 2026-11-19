"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";

import { CertCommentModal } from "@/components/certs/CertCommentModal";
import { fetchCertPdf, saveBytes, toastNotReady, useCertSettings, useRefreshIssued } from "@/hooks/certs";
import { useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { canIssueToNonGraduate, type CertRow } from "@/lib/certs";
import { can } from "@/lib/permissions";
import type { Paged } from "@/lib/reports-types";
import { notify, notifyError } from "@/lib/toast";

type Act = "issue" | "reissue";

/** «Сертификат» of one enrollment on the student card: the valid one, or the way to issue it. */
export function EnrollmentCertificate({ enrollmentId, cohortId, status }: { enrollmentId: string; cohortId: string; status: string }) {
  const { data: me } = useMe();
  const refresh = useRefreshIssued();
  const [act, setAct] = useState<Act | null>(null);
  const sees = !!me && can(me.permissions, "certificates", "view");
  const canChange = !!me && can(me.permissions, "certificates", "change");
  const graduate = status === "выпускник";
  const needsSettings = canChange && !graduate && !!me && can(me.permissions, "cert_templates", "change");

  const valid = useQuery({
    queryKey: ["certificates", "cohort-valid", cohortId],
    queryFn: () => api<Paged<CertRow>>("/api/v1/certificates", { params: { cohort_id: cohortId, status: "valid", page_size: "100" } }),
    enabled: sees,
  });
  const settings = useCertSettings({ enabled: needsSettings });
  const cert = valid.data?.items.find((c) => c.enrollment_id === enrollmentId);

  const download = useMutation({
    mutationFn: async () => {
      const { data, name } = await fetchCertPdf(cert!.id);

      saveBytes(data, name ?? `${cert!.number}.pdf`, "application/pdf");
    },
    onError: notifyError,
  });
  const run = useMutation({
    mutationFn: (text: string) =>
      act === "reissue"
        ? api(`/api/v1/certificates/${cert!.id}/reissue`, { method: "POST", body: { comment: text } })
        : api(`/api/v1/enrollments/${enrollmentId}/certificate`, { method: "POST", body: { comment: text || undefined } }),
    onSuccess: () => {
      void refresh();
      notify(act === "reissue" ? "Сертификат перевыпущен" : "Сертификат выдан");
      setAct(null);
    },
    onError: (e) => {
      void refresh();
      setAct(null);
      if (!toastNotReady(e)) notifyError(e);
    },
  });

  if (!sees || valid.isPending) return <span className="text-default-400">—</span>;

  const mayIssue = canChange && (graduate || (settings.data ? canIssueToNonGraduate(me?.permissions, settings.data.allow_non_graduate) : false));

  return (
    <>
      {cert ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-medium whitespace-nowrap">{cert.number}</span>
          <Button className="h-8 min-w-0 px-2" isLoading={download.isPending} size="sm" variant="light" onPress={() => download.mutate()}>
            Скачать
          </Button>
          {canChange && (
            <Button className="h-8 min-w-0 px-2" size="sm" variant="light" onPress={() => setAct("reissue")}>
              Перевыпустить
            </Button>
          )}
        </div>
      ) : mayIssue ? (
        <Button color="primary" size="sm" variant="flat" onPress={() => setAct("issue")}>
          Выдать
        </Button>
      ) : (
        <span className="text-default-400">—</span>
      )}
      {act && (
        <CertCommentModal
          confirmLabel={act === "reissue" ? "Перевыпустить" : "Выдать"}
          intro={
            act === "reissue"
              ? "Старый сертификат станет «Заменён», выдастся новый с тем же номером и актуальными данными."
              : graduate
                ? "Студенту будет выдан сертификат с новым номером."
                : "Студент не выпускник: сертификат выдаётся по разрешению в настройках, запись попадёт в журнал."
          }
          isLoading={run.isPending}
          label="Комментарий"
          title={act === "reissue" ? "Перевыпустить сертификат" : "Выдать сертификат"}
          required={act === "reissue" || !graduate}
          onClose={() => setAct(null)}
          onSubmit={(text) => run.mutate(text)}
        />
      )}
    </>
  );
}
