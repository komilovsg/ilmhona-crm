"use client";

import clsx from "clsx";
import Link from "next/link";
import { motion } from "framer-motion";

import { EmptyState, QueryState } from "@/components/QueryState";
import { Bone } from "@/components/Skeletons";
import { useCard } from "@/hooks/dash";
import { useReducedMotion } from "@/lib/client-store";
import { type CallLead, type SeatRow, type Tile, type Week, plural, shortDate, whatsappHref } from "@/lib/dash";
import { formatPrice } from "@/lib/education";
import { formatDateTime, telHref } from "@/lib/format";
import { EASE_OUT } from "@/lib/motion";
import { CardSkeleton, DashCard, GrowX, TONE_TEXT } from "./shell";

// ---- queue tiles ----------------------------------------------------------------------------

type TileView = { label: string; hint: string; href: string; accent: string };

function viewOf(t: Tile): TileView {
  switch (t.key) {
    case "callbacks":
      return {
        label: "Перезвонить",
        hint: t.overdue ? `${t.overdue} ${plural(t.overdue, "просрочен", "просрочены", "просрочены")}` : "просрочек нет",
        href: "/leads?tab=callback",
        accent: "border-t-primary",
      };
    case "debtors":
      return { label: "Должники", hint: formatPrice(t.sum), href: "/payments?tab=debtors", accent: "border-t-danger" };
    case "pending":
      return { label: "Подтвердить оплаты", hint: formatPrice(t.sum), href: "/payments?status=ожидает", accent: "border-t-warning" };
    case "new_leads":
      return { label: "Новые лиды", hint: "за сегодня", href: "/leads", accent: "border-t-success" };
  }
}

export function QueuesCard({ branch }: { branch: string }) {
  const query = useCard<{ tiles: Tile[] }>("queues", branch);
  const reduced = useReducedMotion();

  return (
    <QueryState
      query={query}
      skeleton={
        <div className="grid grid-cols-2 gap-3.5 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Bone key={i} className="h-[8.25rem] rounded-[1.125rem]" />
          ))}
        </div>
      }
    >
      {(d) => (
        <ul className="grid grid-cols-[repeat(auto-fit,minmax(9.5rem,1fr))] gap-3.5" aria-label="Очереди на сегодня">
          {d.tiles.map((t, i) => {
            const v = viewOf(t);

            return (
              <motion.li
                key={t.key}
                initial={reduced ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: reduced ? 0 : 0.5, ease: EASE_OUT, delay: reduced ? 0 : i * 0.06 }}
              >
                <Link
                  className={clsx("flex h-[8.25rem] min-w-0 flex-col gap-1.5 rounded-[1.125rem] border-t-[3px] bg-content1 p-4 transition-colors hover:bg-content2 md:p-5", v.accent)}
                  href={v.href}
                >
                  <span className="truncate text-[0.8125rem] text-default-500 md:text-sm">{v.label}</span>
                  <span className="font-display text-[2.5rem] font-bold leading-none tabular-nums">{t.count}</span>
                  <span className="truncate text-[0.8125rem] text-default-500">{v.hint}</span>
                </Link>
              </motion.li>
            );
          })}
        </ul>
      )}
    </QueryState>
  );
}

// ---- call queue -----------------------------------------------------------------------------

const BTN = "inline-flex h-10 items-center justify-center rounded-[0.625rem] px-3.5 text-sm font-semibold transition-opacity hover:opacity-90";

export function CallQueueCard({ branch }: { branch: string }) {
  const query = useCard<{ count: number; items: CallLead[] }>("call-queue", branch);

  return (
    <DashCard
      aside={<span className="text-[0.8125rem] text-default-500">{query.data ? `${query.data.count} · ` : ""}перезвонить сегодня</span>}
      delay={0.1}
      title="Очередь звонков"
    >
      <QueryState
        bare
        empty={<EmptyState bare hint="Звонки появятся, когда у лида назначен перезвон." title="На сегодня звонков нет" />}
        isEmpty={(d) => d.items.length === 0}
        query={query}
        skeleton={<CardSkeleton rowClass="h-[4.5rem]" rows={3} />}
      >
        {(d) => (
          <div className="flex flex-col gap-2.5">
            <ul className="flex flex-col gap-2.5">
              {d.items.map((l) => (
                <li key={l.id} className="flex min-h-[4.5rem] flex-wrap items-center justify-between gap-x-4 gap-y-2.5 rounded-xl bg-content2 px-3.5 py-3">
                  <span className="flex min-w-0 flex-1 basis-48 flex-col gap-0.5">
                    <span className="truncate text-[0.9375rem] font-semibold">{l.full_name}</span>
                    <span className="truncate text-[0.8125rem] text-default-500">
                      {[l.course_name, l.status, l.next_contact_at && formatDateTime(l.next_contact_at)].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                  {l.phone ? (
                    <span className="flex gap-2">
                      <a className={clsx(BTN, "bg-primary text-primary-foreground")} href={telHref(l.phone)}>
                        Позвонить
                      </a>
                      <a className={clsx(BTN, "bg-success/15 text-success-700 dark:text-success")} href={whatsappHref(l.phone)} rel="noreferrer" target="_blank">
                        WhatsApp
                      </a>
                    </span>
                  ) : (
                    <span className="text-[0.8125rem] text-default-500">нет телефона</span>
                  )}
                </li>
              ))}
            </ul>
            {d.count > d.items.length && (
              <Link className="text-sm text-brand-text" href="/leads?tab=callback">
                Все звонки · {d.count}
              </Link>
            )}
          </div>
        )}
      </QueryState>
    </DashCard>
  );
}

// ---- seats ----------------------------------------------------------------------------------

export function SeatsCard({ branch }: { branch: string }) {
  const query = useCard<{ items: SeatRow[] }>("seats", branch);

  return (
    <DashCard delay={0.18} title="Наборы: свободные места">
      <QueryState
        bare
        empty={<EmptyState bare hint="Потоки на наборе появятся здесь." title="Наборов сейчас нет" />}
        isEmpty={(d) => d.items.length === 0}
        query={query}
        skeleton={<CardSkeleton rowClass="h-[4.25rem]" rows={2} />}
      >
        {(d) => (
          <ul className="flex flex-col gap-3.5">
            {d.items.map((s, i) => (
              <li key={s.id}>
                <Link className="flex min-h-[4.25rem] flex-col gap-1.5 rounded-lg hover:bg-content2" href={`/cohorts/${s.id}`}>
                  <span className="flex justify-between gap-2.5 text-sm">
                    <span className="min-w-0 truncate">
                      <b>{s.code}</b> {s.course_name}
                    </span>
                    <span className="shrink-0 text-default-500">старт {shortDate(s.start_date)}</span>
                  </span>
                  <span className="h-2 overflow-hidden rounded-full bg-default-200">
                    <GrowX className="h-2 rounded-full" delay={0.2 + i * 0.07} style={{ width: `${Math.min(s.fill_pct, 100)}%`, background: "var(--chart-fill)" }} />
                  </span>
                  <span className={clsx("text-[0.8125rem]", s.over_capacity ? "font-medium text-warning-600 dark:text-warning" : "text-default-500")}>
                    {s.over_capacity ? `${s.enrolled} из ${s.capacity} · сверх плана` : `свободно ${s.free} из ${s.capacity}`}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </DashCard>
  );
}

// ---- week -----------------------------------------------------------------------------------

function Change({ n }: { n: number | null }) {
  if (n === null || n === 0) return null;

  return <span className={clsx("ml-1", n > 0 ? TONE_TEXT.up : TONE_TEXT.down)}>{n > 0 ? "▲" : "▼"} {Math.abs(n)}</span>;
}

export function WeekCard({ branch }: { branch: string }) {
  const query = useCard<Week>("week", branch);

  return (
    <DashCard className="py-4 md:py-5" delay={0.26} label="Неделя">
      <QueryState bare query={query} skeleton={<Bone className="h-12 w-full rounded-xl md:h-6" />}>
        {(w) => (
          <div className="flex flex-wrap items-center gap-x-10 gap-y-2.5">
            <h2 className="font-display text-base font-semibold text-default-500">Неделя</h2>
            {w.leads !== null && (
              <span className="text-[0.9375rem]">
                лидов <b>{w.leads}</b>
                <Change n={w.leads_change} />
              </span>
            )}
            <span className="text-[0.9375rem]">
              записались <b>{w.enrolled}</b>
              <Change n={w.enrolled_change} />
            </span>
            {w.payments_count !== null && w.payments_sum !== null && (
              <span className="text-[0.9375rem]">
                оплат <b>{w.payments_count} · {formatPrice(w.payments_sum)}</b>
              </span>
            )}
            {w.debt !== null && (
              <span className="text-[0.9375rem]">
                долг филиала <b>{formatPrice(w.debt)}</b>
              </span>
            )}
          </div>
        )}
      </QueryState>
    </DashCard>
  );
}
