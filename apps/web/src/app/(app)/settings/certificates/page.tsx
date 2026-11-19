"use client";

import { useState } from "react";

import { DirectorTab } from "@/components/cert/DirectorTab";
import { RulesTab } from "@/components/cert/RulesTab";
import { TemplatesTab } from "@/components/cert/TemplatesTab";
import { PageHeader } from "@/components/PageHeader";
import { Segmented } from "@/components/Segmented";

type Tab = "templates" | "director" | "rules";

export default function CertificatesSettingsPage() {
  const [tab, setTab] = useState<Tab>("templates");

  return (
    <>
      <p className="mb-1 text-sm text-default-500">Настройки</p>
      <PageHeader title="Сертификаты" />
      <Segmented
        className="mb-5"
        label="Раздел"
        options={[
          { key: "templates", label: "Шаблоны" },
          { key: "director", label: "Директор и печать" },
          { key: "rules", label: "Правила" },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "templates" && <TemplatesTab />}
      {tab === "director" && <DirectorTab />}
      {tab === "rules" && <RulesTab />}
    </>
  );
}
