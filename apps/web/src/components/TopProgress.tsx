"use client";

import { useIsFetching, useIsMutating } from "@tanstack/react-query";

/**
 * Thin bar at the top while anything loads or saves. A refetch keeps the old data on screen and
 * this is the only sign of it. It appears after 150 ms (fast requests show nothing).
 */
export function TopProgress() {
  const busy = useIsFetching() + useIsMutating() > 0;

  if (!busy) return null;

  return (
    <div
      aria-hidden="true"
      className="appear-late fixed inset-x-0 top-0 z-[60] h-0.5 overflow-hidden bg-primary/20"
      style={{ "--late": "150ms" } as React.CSSProperties}
    >
      <div className="sweep h-full w-1/3 bg-primary" />
    </div>
  );
}
