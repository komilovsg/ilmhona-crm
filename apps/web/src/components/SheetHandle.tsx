"use client";

import { useEffect, useRef } from "react";
import { animate, motionValue, type AnimationPlaybackControls } from "framer-motion";

import { useIsPhone, useReducedMotion } from "@/lib/client-store";
import { DRAG_SLOP, sheetOffset, shouldCloseSheet, velocityOf, type Sample } from "@/lib/sheet";

/** Nearest ancestor of `el` (up to `stop`) that actually scrolls vertically. */
function scrollParent(el: HTMLElement | null, stop: HTMLElement): HTMLElement | null {
  for (; el && el !== stop; el = el.parentElement) {
    const oy = getComputedStyle(el).overflowY;

    if ((oy === "auto" || oy === "scroll") && el.scrollHeight > el.clientHeight + 1) return el;
  }

  return null;
}

/**
 * The grab handle of a bottom sheet and the whole swipe-to-close behaviour of the dialog it sits in
 * (put it first inside a Modal / Drawer content). Phone only; renders nothing on desktop.
 *
 * Direct manipulation (apple-design): the dialog follows the finger 1:1 from where it was grabbed, resists
 * upwards (rubber-band), and on release either closes (distance or flick velocity, carried into the spring) or
 * springs back; a new touch during the animation grabs the sheet where it is. Content that scrolls drags the
 * sheet only when it is already at the top and the finger moves down. Touch events are used (not pointer
 * events) because the browser must be told per move whether it may scroll.
 *
 * `canClose` runs on release before closing: return false to keep the sheet (the unsaved-changes guard shows
 * its question there). `onClose` is called once the sheet has left the screen.
 */
export function SheetHandle({ onClose, canClose }: { onClose: () => void; canClose?: () => boolean }) {
  const phone = useIsPhone();
  const reduced = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const callbacks = useRef({ onClose, canClose, reduced });

  useEffect(() => {
    callbacks.current = { onClose, canClose, reduced };
  });

  useEffect(() => {
    const dialog = ref.current?.closest<HTMLElement>('[role="dialog"]');

    if (!phone || !dialog) return;

    const wrapper = dialog.closest<HTMLElement>('[data-slot="wrapper"]');
    const backdrop = wrapper?.previousElementSibling instanceof HTMLElement ? wrapper.previousElementSibling : null;
    const offset = motionValue(0);
    let running: AnimationPlaybackControls | null = null;
    let mode: "idle" | "pending" | "drag" | "ignore" = "idle";
    let x0 = 0;
    let y0 = 0;
    let start = 0;
    let scroller: HTMLElement | null = null;
    let samples: Sample[] = [];

    const unsub = offset.on("change", (v) => {
      dialog.style.translate = v ? `0 ${v}px` : "";
      if (backdrop) backdrop.style.opacity = v > 0 ? String(Math.max(0, 1 - v / (dialog.offsetHeight || 1))) : "";
    });

    const springBack = (velocity: number) => {
      if (callbacks.current.reduced) offset.set(0);
      else running = animate(offset, 0, { type: "spring", bounce: 0.15, duration: 0.35, velocity });
    };

    const dismiss = (velocity: number) => {
      const done = () => callbacks.current.onClose();

      if (callbacks.current.reduced) {
        // no slide: fade out where the finger left it
        running = animate(dialog, { opacity: 0 }, { duration: 0.12, onComplete: done });
      } else {
        running = animate(offset, dialog.offsetHeight + 40, {
          type: "spring",
          bounce: 0,
          duration: 0.3,
          velocity,
          restDelta: 2,
          onComplete: done,
        });
      }
    };

    const onStart = (e: TouchEvent) => {
      if (e.touches.length !== 1) {
        mode = "ignore";

        return;
      }
      const t = e.touches[0];

      x0 = t.clientX;
      y0 = t.clientY;
      scroller = scrollParent(e.target as HTMLElement, dialog);
      samples = [{ y: t.clientY, t: e.timeStamp }];
      start = offset.get();
      if (running && start !== 0) {
        // interrupted mid-animation: grab the sheet where it is on screen
        running.stop();
        running = null;
        mode = "drag";
      } else {
        mode = "pending";
      }
    };

    const onMove = (e: TouchEvent) => {
      if (mode === "idle" || mode === "ignore") return;
      const t = e.touches[0];
      const dy = t.clientY - y0;

      if (mode === "pending") {
        if (Math.abs(dy) < DRAG_SLOP && Math.abs(t.clientX - x0) < DRAG_SLOP) return;
        if (Math.abs(t.clientX - x0) > Math.abs(dy) || dy < 0 || (scroller && scroller.scrollTop > 0)) {
          mode = "ignore"; // a horizontal move, a scroll, or a pull up: not ours
          return;
        }
        mode = "drag";
        y0 = t.clientY; // start from here, the 10 px of hysteresis do not make the sheet jump
        samples = [];
      }
      if (e.cancelable) e.preventDefault();
      samples.push({ y: t.clientY, t: e.timeStamp });
      offset.set(sheetOffset(start + (t.clientY - y0), dialog.offsetHeight));
    };

    const onEnd = () => {
      const was = mode;

      mode = "idle";
      if (was !== "drag") return;
      const velocity = velocityOf(samples);
      const height = dialog.offsetHeight;

      if (shouldCloseSheet({ offset: offset.get(), velocity, height }) && callbacks.current.canClose?.() !== false) dismiss(velocity);
      else springBack(velocity);
    };

    dialog.addEventListener("touchstart", onStart, { passive: true });
    dialog.addEventListener("touchmove", onMove, { passive: false });
    dialog.addEventListener("touchend", onEnd);
    dialog.addEventListener("touchcancel", onEnd);

    // Keyboard: keep the sheet in the visible part of the screen and the focused field above the keyboard.
    const vv = window.visualViewport;
    const fit = () => {
      if (wrapper && vv) wrapper.style.top = `${vv.offsetTop}px`;
      const el = document.activeElement;

      if (el instanceof HTMLElement && dialog.contains(el) && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) {
        el.scrollIntoView({ block: "nearest", behavior: callbacks.current.reduced ? "auto" : "smooth" });
      }
    };
    const onFocusIn = () => window.setTimeout(fit, 300);

    vv?.addEventListener("resize", fit);
    vv?.addEventListener("scroll", fit);
    dialog.addEventListener("focusin", onFocusIn);

    return () => {
      dialog.removeEventListener("touchstart", onStart);
      dialog.removeEventListener("touchmove", onMove);
      dialog.removeEventListener("touchend", onEnd);
      dialog.removeEventListener("touchcancel", onEnd);
      dialog.removeEventListener("focusin", onFocusIn);
      vv?.removeEventListener("resize", fit);
      vv?.removeEventListener("scroll", fit);
      running?.stop();
      unsub();
      if (wrapper) wrapper.style.top = "";
    };
  }, [phone]);

  if (!phone) return null;

  return (
    <div ref={ref} aria-hidden className="flex shrink-0 justify-center pb-1 pt-2.5" data-sheet-handle="">
      <span className="h-1 w-10 rounded-full bg-default-300" />
    </div>
  );
}
