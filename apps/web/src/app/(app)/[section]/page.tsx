import { notFound } from "next/navigation";

import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { NAV_ITEMS } from "@/lib/permissions";

/** Sections of later stages: the nav works, the page says it is coming. */
export default async function SectionPage({ params }: PageProps<"/[section]">) {
  const { section } = await params;
  const item = NAV_ITEMS.find((i) => i.href === `/${section}`);

  if (!item) notFound();

  return (
    <>
      <PageHeader title={item.label} />
      <div className="flex flex-col items-center gap-3 rounded-2xl bg-content1 px-6 py-16 text-center">
        <span className="rounded-full bg-primary/10 p-4 text-brand-text">
          <Icon name={item.icon} size={28} />
        </span>
        <h2 className="text-lg font-semibold">Скоро</h2>
        <p className="max-w-sm text-sm text-default-500">Этот раздел появится в одном из следующих этапов.</p>
      </div>
    </>
  );
}
