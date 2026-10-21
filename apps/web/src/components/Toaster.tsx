"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { AnimatePresence, motion, useMotionValue, type PanInfo, type Variants } from "framer-motion";

import { useIsPhone, useReducedMotion } from "@/lib/client-store";
import { toastSwipe, type SwipeDir } from "@/lib/sheet";
import { dismissToast, getServerToasts, getToasts, subscribeToasts, TOAST_MS, type Toast } from "@/lib/toast-store";

const OFF = "calc(100% + 24px)";

/** Desktop slides in from the right edge, phone drops from the top; reduced motion only fades. */
function variantsFor(phone: boolean, reduced: boolean): Variants {
  if (reduced) {
    return {
      hidden: { opacity: 0 },
      shown: { opacity: 1, transition: { duration: 0.12 } },
      gone: { opacity: 0, transition: { duration: 0.1 } },
    };
  }

  const away = phone ? { y: `calc(-100% - 24px)` } : { x: OFF };

  return {
    hidden: { opacity: 0, ...away },
    shown: { opacity: 1, x: 0, y: 0, transition: { type: "spring", duration: 0.38, bounce: 0.12 } },
    // a swiped toast leaves the way it was thrown
    gone: (dir?: SwipeDir) => ({
      opacity: 0,
      ...(dir === "left" ? { x: "-120%" } : dir === "right" ? { x: "120%" } : dir === "up" ? { y: "calc(-100% - 24px)" } : away),
      transition: { duration: 0.22, ease: [0.4, 0, 1, 1] },
    }),
  };
}

/** Counts down while not paused (hover, focus, finger down); a resumed toast keeps at least 1.5 s. */
function useCountdown(ms: number, paused: boolean, onDone: () => void) {
  const left = useRef(ms);
  const done = useRef(onDone);

  useEffect(() => {
    done.current = onDone;
  });
  useEffect(() => {
    if (paused) return;
    const startedAt = Date.now();
    const id = window.setTimeout(() => done.current(), left.current);

    return () => {
      window.clearTimeout(id);
      left.current = Math.max(1500, left.current - (Date.now() - startedAt));
    };
  }, [paused]);
}

function ToastItem({ toast, phone, reduced }: { toast: Toast; phone: boolean; reduced: boolean }) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [thrown, setThrown] = useState<SwipeDir | null>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const close = useCallback(() => dismissToast(toast.id), [toast.id]);

  useCountdown(TOAST_MS[toast.kind], hovered || focused || dragging, close);

  // a swipe sets `thrown`; the next render carries it to the exit variant, then the toast is removed
  useEffect(() => {
    if (thrown) close();
  }, [thrown, close]);

  function onDragEnd(_: unknown, info: PanInfo) {
    setDragging(false);
    const dir = toastSwipe({ dx: info.offset.x, dy: info.offset.y, vx: info.velocity.x, vy: info.velocity.y });

    if (dir) setThrown(dir);
  }

  return (
    <motion.li
      animate="shown"
      custom={thrown ?? undefined}
      data-toast=""
      exit="gone"
      initial="hidden"
      layout={reduced ? false : "position"}
      variants={variantsFor(phone, reduced)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setFocused(false);
      }}
      onFocus={() => setFocused(true)}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
    >
      {/* the li enters / leaves; this inner box is the one under the finger (separate motion values, so the
          enter animation never fights the drag) */}
      <motion.div
        className={`pointer-events-auto flex items-start gap-2 rounded-xl border border-default-200 border-l-4 bg-content1 py-2.5 pl-3 pr-1.5 text-sm text-foreground shadow-lg ${
          toast.kind === "error" ? "border-l-danger" : "border-l-success"
        }`}
        data-kind={toast.kind}
        drag={phone}
        dragConstraints={{ left: 0, right: 0, top: 0, bottom: 0 }}
        dragElastic={{ top: 1, left: 1, right: 1, bottom: 0.12 }}
        dragMomentum={false}
        style={{ x, y, touchAction: phone ? "none" : undefined }}
        onDragEnd={onDragEnd}
        onDragStart={() => setDragging(true)}
      >
        <span className="min-w-0 flex-1 break-words py-1">{toast.title}</span>
        <button
          aria-label="Закрыть уведомление"
          className="grid size-8 shrink-0 place-items-center rounded-lg text-default-500 outline-none hover:bg-default-100 focus-visible:ring-2 focus-visible:ring-primary"
          type="button"
          onClick={close}
        >
          <svg aria-hidden className="size-4" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </motion.div>
    </motion.li>
  );
}

/**
 * The one toast stack. Desktop: bottom right. Phone: top, over the header, below the notch. Fixed, so it never
 * shifts the page. `data-react-aria-top-layer` keeps a click on a toast from counting as «outside» for an open
 * modal; screen readers hear the text through the two live regions (polite, errors assertive).
 */
export function Toaster() {
  const toasts = useSyncExternalStore(subscribeToasts, getToasts, getServerToasts);
  const phone = useIsPhone();
  const reduced = useReducedMotion();

  return (
    <>
      <div aria-live="polite" className="sr-only" data-live-announcer="true">
        {toasts.filter((t) => t.kind === "success").map((t) => <p key={t.id}>{t.title}</p>)}
      </div>
      <div aria-live="assertive" className="sr-only" data-live-announcer="true" role="alert">
        {toasts.filter((t) => t.kind === "error").map((t) => <p key={t.id}>{t.title}</p>)}
      </div>
      <ul
        className={
          phone
            ? "pointer-events-none fixed inset-x-0 top-0 z-[110] flex flex-col gap-2 px-3 pt-[calc(env(safe-area-inset-top)+8px)]"
            : "pointer-events-none fixed bottom-4 right-4 z-[110] flex w-[380px] max-w-[calc(100vw-2rem)] flex-col gap-2"
        }
        data-react-aria-top-layer="true"
        data-toaster=""
      >
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <ToastItem key={t.id} phone={phone} reduced={reduced} toast={t} />
          ))}
        </AnimatePresence>
      </ul>
    </>
  );
}
