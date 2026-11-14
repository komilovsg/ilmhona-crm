"use client";

import { useState } from "react";
import { Button } from "@heroui/button";
import { Drawer, DrawerBody, DrawerContent, DrawerFooter, DrawerHeader } from "@heroui/drawer";
import { Switch } from "@heroui/switch";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Reorder, useDragControls } from "framer-motion";

import { ConflictDialog } from "@/components/ConflictDialog";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { SheetHandle } from "@/components/SheetHandle";
import { LAYOUT_KEY, LAYOUT_PATH } from "@/hooks/dash";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import { useIsPhone, useReducedMotion } from "@/lib/client-store";
import { layoutBody, moveCard, type Layout, type LayoutCard } from "@/lib/dash";
import { useOverlayMotion } from "@/lib/motion";
import { notify, notifyError } from "@/lib/toast";

type Body = { order: string[]; hidden: string[] };

/** The saved order and switches put back on the cards (cards the body does not know keep their place at the end). */
function applyBody(cards: LayoutCard[], body: Body): LayoutCard[] {
  const by = new Map(cards.map((c) => [c.id, c]));
  const ordered = body.order.flatMap((id) => (by.has(id) ? [by.get(id)!] : []));
  const rest = cards.filter((c) => !body.order.includes(c.id));

  return [...ordered, ...rest].map((c) => ({ ...c, visible: !body.hidden.includes(c.id) }));
}

function Row({
  card,
  first,
  last,
  onToggle,
  onMove,
}: {
  card: LayoutCard;
  first: boolean;
  last: boolean;
  onToggle: (visible: boolean) => void;
  onMove: (delta: -1 | 1) => void;
}) {
  const controls = useDragControls();
  const reduced = useReducedMotion();

  return (
    <Reorder.Item
      as="li"
      className="relative flex min-h-14 items-center gap-1.5 rounded-xl bg-content2 py-1.5 pl-1 pr-2"
      dragControls={controls}
      dragListener={false}
      transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 40 }}
      value={card}
      whileDrag={reduced ? undefined : { scale: 1.02, boxShadow: "0 8px 24px rgb(0 0 0 / 0.25)", zIndex: 20 }}
    >
      <button
        aria-label={`Перетащить: ${card.title}`}
        className="flex size-11 shrink-0 cursor-grab touch-none select-none items-center justify-center rounded-lg text-default-500 hover:bg-default-200 active:cursor-grabbing"
        type="button"
        onPointerDown={(e) => controls.start(e)}
      >
        <Icon name="grip" size={22} />
      </button>
      <Switch
        classNames={{ base: "m-0 min-w-0 max-w-none flex-1 flex-row-reverse justify-between gap-3", label: clsx("truncate text-sm", !card.visible && "text-default-500") }}
        isSelected={card.visible}
        size="sm"
        onValueChange={onToggle}
      >
        {card.title}
        <span className="sr-only">{card.visible ? ": показана" : ": скрыта"}</span>
      </Switch>
      <span className="flex shrink-0">
        <button
          aria-label={`Выше: ${card.title}`}
          className="flex size-8 items-center justify-center rounded-lg text-default-500 hover:bg-default-200 hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent [@media(pointer:coarse)]:size-10"
          disabled={first}
          type="button"
          onClick={() => onMove(-1)}
        >
          <Icon name="arrow-up" size={18} />
        </button>
        <button
          aria-label={`Ниже: ${card.title}`}
          className="flex size-8 items-center justify-center rounded-lg text-default-500 hover:bg-default-200 hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent [@media(pointer:coarse)]:size-10"
          disabled={last}
          type="button"
          onClick={() => onMove(1)}
        >
          <Icon name="arrow-down" size={18} />
        </button>
      </span>
    </Reorder.Item>
  );
}

function Panel({ layout, close }: { layout: Layout; close: () => void }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<LayoutCard[]>(layout.cards);

  const save = useVersionedSave({
    record: layout,
    values: layoutBody(draft),
    toValues: (l: Layout) => layoutBody(l.cards),
    apply: (v) => setDraft((d) => applyBody(d, v)),
    request: (_changed, version, all) => api<Layout>(LAYOUT_PATH, { method: "PUT", body: all, version }),
    labels: { order: "Порядок карточек", hidden: "Скрытые карточки" },
    show: {
      order: (ids: string[]) => ids.map((id) => layout.cards.find((c) => c.id === id)?.title ?? id).join(" → "),
      hidden: (ids: string[]) => ids.map((id) => layout.cards.find((c) => c.id === id)?.title ?? id).join(", ") || "нет",
    },
    onSaved: (result) => {
      if (result) queryClient.setQueryData(LAYOUT_KEY, result);
      notify("Дашборд настроен");
      close();
    },
  });

  const reset = useMutation({
    mutationFn: () => api<Layout>(LAYOUT_PATH, { method: "PUT", body: { reset: true }, version: layout.version }),
    onSuccess: (result) => {
      queryClient.setQueryData(LAYOUT_KEY, result);
      notify("Вернули как было");
      close();
    },
    onError: (e) => {
      notifyError(e);
      void queryClient.invalidateQueries({ queryKey: LAYOUT_KEY });
    },
  });

  const toggle = (id: string, visible: boolean) => setDraft((d) => d.map((c) => (c.id === id ? { ...c, visible } : c)));

  return (
    <>
      <DrawerBody className="gap-3 pb-2">
        <p className="text-sm text-default-500">
          Потяните за ручку, чтобы поменять порядок, или нажмите стрелки. Выключатель скрывает карточку; права доступа он не меняет.
        </p>
        <Reorder.Group as="ul" axis="y" className="flex flex-col gap-2" values={draft} onReorder={setDraft}>
          {draft.map((c, i) => (
            <Row
              key={c.id}
              card={c}
              first={i === 0}
              last={i === draft.length - 1}
              onMove={(delta) => setDraft((d) => moveCard(d, { id: c.id, delta }))}
              onToggle={(v) => toggle(c.id, v)}
            />
          ))}
        </Reorder.Group>
      </DrawerBody>
      <DrawerFooter className="flex-wrap justify-between">
        <LoadingButton isDisabled={layout.is_default} isLoading={reset.isPending} variant="light" onPress={() => reset.mutate()}>
          Вернуть как было
        </LoadingButton>
        <span className="flex gap-2">
          <Button variant="light" onPress={close}>
            Отмена
          </Button>
          <LoadingButton color="primary" isLoading={save.pending} onPress={() => void save.save(layoutBody(draft))}>
            Сохранить
          </LoadingButton>
        </span>
      </DrawerFooter>
      <ConflictDialog save={save} />
    </>
  );
}

/** «Настроить»: which cards this user may have, a switch and a place for each. Saved per user on the server. */
export function CustomizePanel({ layout, isOpen, onOpenChange }: { layout: Layout; isOpen: boolean; onOpenChange: (open: boolean) => void }) {
  const phone = useIsPhone();
  const overlayMotion = useOverlayMotion();

  return (
    <Drawer isOpen={isOpen} motionProps={overlayMotion} placement={phone ? "bottom" : "right"} scrollBehavior="inside" onOpenChange={onOpenChange}>
      <DrawerContent>
        {(close) => (
          <>
            <SheetHandle onBackdrop={close} onClose={close} />
            <DrawerHeader className="font-display">Настроить дашборд</DrawerHeader>
            <Panel close={close} layout={layout} />
          </>
        )}
      </DrawerContent>
    </Drawer>
  );
}
