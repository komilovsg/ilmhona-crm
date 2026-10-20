"use client";

import { Pagination } from "@heroui/pagination";

export function Pager({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));

  if (pages <= 1) return null;

  return (
    <div className="mt-4 flex justify-center">
      <Pagination isCompact showControls page={page} total={pages} onChange={onChange} />
    </div>
  );
}
