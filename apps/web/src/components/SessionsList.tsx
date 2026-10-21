"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";

import { Icon } from "./Icon";
import { EmptyState, QueryState } from "./QueryState";
import { ListSkeleton } from "./Skeletons";

import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { notify, notifyError } from "@/lib/toast";
import type { SessionRow } from "@/lib/types";

/**
 * Active sessions (one per signed-in device). `base` is `/api/v1/auth` for the user's own list,
 * `/api/v1/users/<id>` for a superadmin looking at somebody else's. Ending the current one signs out.
 */
export function SessionsList({ base, own = false, onSignedOut }: { base: string; own?: boolean; onSignedOut?: () => void }) {
  const queryClient = useQueryClient();
  const key = ["sessions", base];
  const list = useQuery({ queryKey: key, queryFn: () => api<SessionRow[]>(`${base}/sessions`) });
  const end = useMutation({
    mutationFn: async (s: SessionRow) => {
      await api(`${base}/sessions/${s.id}`, { method: "DELETE" });

      return s;
    },
    onSuccess: (s) => {
      if (s.current) {
        onSignedOut?.();

        return;
      }
      void queryClient.invalidateQueries({ queryKey: key });
      notify("Сеанс завершён");
    },
    onError: notifyError,
  });
  const others = useMutation({
    mutationFn: () => api<{ ended: number }>(`${base}/sessions/end-others`, { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: key });
      notify("Вы вышли на всех других устройствах");
    },
    onError: notifyError,
  });
  const rows = list.data ?? [];

  return (
    <QueryState
      empty={<EmptyState title="Нет активных сеансов" />}
      isEmpty={(d) => d.length === 0}
      query={list}
      skeleton={<ListSkeleton cols={3} rows={2} />}
    >
      <div className="space-y-3">
        <ul className="divide-y divide-divider">
          {rows.map((s) => (
            <li key={s.id} className="flex items-center gap-3 py-3">
              <span className="text-default-500">
                <Icon name={/iOS|Android/.test(s.device) ? "phone" : "system"} size={22} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 font-medium">
                  {s.device}
                  {s.current && (
                    <Chip color="primary" size="sm" variant="flat">
                      Это устройство
                    </Chip>
                  )}
                </div>
                <div className="text-xs text-default-500">
                  Вход {formatDateTime(s.created_at)} · активность {formatDateTime(s.last_used_at)}
                  {s.remember ? " · запомнен" : ""}
                </div>
              </div>
              <Button
                aria-label={`Выйти на устройстве ${s.device}`}
                color="danger"
                isLoading={end.isPending && end.variables?.id === s.id}
                size="sm"
                variant="light"
                onPress={() => end.mutate(s)}
              >
                {own && s.current ? "Выйти" : "Выйти на этом устройстве"}
              </Button>
            </li>
          ))}
        </ul>
        {own && rows.some((s) => !s.current) && (
          <Button color="danger" isLoading={others.isPending} variant="flat" onPress={() => others.mutate()}>
            Выйти на всех других устройствах
          </Button>
        )}
      </div>
    </QueryState>
  );
}
