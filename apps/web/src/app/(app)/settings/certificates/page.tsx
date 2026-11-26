"use client";

import { useState } from "react";

import { DirectorTab } from "@/components/cert/DirectorTab";
import { IssueSettingsTab } from "@/components/cert/IssueSettingsTab";
import { RulesTab } from "@/components/cert/RulesTab";
import { TemplatesTab } from "@/components/cert/TemplatesTab";
import { PageHeader } from "@/components/PageHeader";
import { Segmented } from "@/components/Segmented";
import { useIsSuperadmin } from "@/hooks/goals";

type Tab = "templates" | "director" | "rules" | "issue";

export default function CertificatesSettingsPage() {
  const [tab, setTab] = useState<Tab>("templates");
  const superadmin = useIsSuperadmin();

  return (
    <>
      <p className="mb-1 text-sm text-default-500">Настройки</p>
      <PageHeader title="Шаблоны сертификатов" />
      <Segmented
        className="mb-5"
        label="Раздел"
        options={[
          { key: "templates", label: "Шаблоны" },
          { key: "director", label: "Директор и печать" },
          { key: "rules", label: "Правила" },
          ...(superadmin ? [{ key: "issue" as const, label: "Выдача" }] : []),
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "templates" && <TemplatesTab />}
      {tab === "director" && <DirectorTab />}
      {tab === "rules" && <RulesTab />}
      {tab === "issue" && superadmin && <IssueSettingsTab />}
    </>
  );
}
