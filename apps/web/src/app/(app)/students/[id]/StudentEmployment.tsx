"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";


import { Icon } from "@/components/Icon";
import { RowMenu } from "@/components/RowMenu";
import { useCanChangeGraduates, useCanSeeGraduates } from "@/hooks/reports";
import { api } from "@/lib/api";
import { fullDate } from "@/lib/education";
import type { EmploymentRow, Paged } from "@/lib/reports-types";

const EmploymentFormModal = dynamic(() => import("../../graduates/EmploymentFormModal").then((m) => m.EmploymentFormModal));

/** The student's jobs (the one employment table). Adding needs a graduate enrollment. */
export function StudentEmployment({ student, graduateEnrollmentId }: { student: { id: string; name: string }; graduateEnrollmentId: string | null }) {
  const sees = useCanSeeGraduates();
  const canChange = useCanChangeGraduates();
  const [editing, setEditing] = useState<EmploymentRow | "new" | null>(null);
  const jobs = useQuery({
    queryKey: ["employment", { student: student.id }],
    queryFn: () => api<Paged<EmploymentRow>>("/api/v1/employment", { params: { student_id: student.id, page_size: "50" } }),
    enabled: sees,
  });

  if (!sees || !jobs.data || (jobs.data.items.length === 0 && !(canChange && graduateEnrollmentId))) return null;

  return (
    <section className="mt-8">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Трудоустройство</h2>
        {canChange && graduateEnrollmentId && (
          <Button size="sm" startContent={<Icon name="plus" size={16} />} variant="flat" onPress={() => setEditing("new")}>
            Добавить
          </Button>
        )}
      </div>
      <ul className="space-y-2">
        {jobs.data.items.map((j) => (
          <li key={j.id} className="flex items-start justify-between gap-2 rounded-2xl bg-content1 p-4">
            <div className="min-w-0">
              <div className="font-medium">{j.organization}</div>
              <div className="text-sm text-default-500">{[j.position, fullDate(j.employed_at)].filter(Boolean).join(" · ")}</div>
            </div>
            {canChange && <RowMenu actions={[{ key: "edit", label: "Изменить", icon: "edit" }]} label={`Действия: ${j.organization}`} onAction={() => setEditing(j)} />}
          </li>
        ))}
      </ul>
      {editing && (
        <EmploymentFormModal
          enrollmentId={graduateEnrollmentId}
          job={editing === "new" ? null : editing}
          student={student}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}
