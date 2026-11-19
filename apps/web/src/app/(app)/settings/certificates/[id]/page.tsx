"use client";

import { use, useState } from "react";
import Link from "next/link";

import { Constructor } from "@/components/cert/editor/Constructor";
import { EmptyState, QueryState } from "@/components/QueryState";
import { Bone } from "@/components/Skeletons";
import { useTemplate } from "@/hooks/certs";
import type { TemplateDetail } from "@/lib/cert-editor/types";

export default function ConstructorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const query = useTemplate(id);
  const [next, setNext] = useState<{ d: TemplateDetail; n: number } | null>(null);

  return (
    <QueryState
      errorText="Не удалось загрузить шаблон"
      notFound={
        <EmptyState action={<Link className="text-brand-text" href="/settings/certificates">К шаблонам</Link>} title="Шаблон не найден" />
      }
      query={query}
      skeleton={<Bone className="h-[60vh] w-full" />}
    >
      {(d) => <Constructor key={next?.n ?? 0} initial={next?.d ?? d} onReplace={(nd) => setNext({ d: nd, n: (next?.n ?? 0) + 1 })} />}
    </QueryState>
  );
}
