// Shared motion presets (framer-motion, the library HeroUI already ships with; `motion` is its new name).
// Rules: 150-250 ms, springs where the thing is touched, transform + opacity only (no layout shift),
// and nothing moves under prefers-reduced-motion (followed live): our own motion reads useReducedMotion, every
// HeroUI overlay gets a fade-only motionProps (<MotionConfig reducedMotion> does not stop their
// slides: measured), and globals.css keeps a transform safety net.

import type { Transition } from "framer-motion";

import { useReducedMotion } from "./client-store";

/** Touch feedback and small state changes: quick, no overshoot. */
export const SPRING_SNAPPY: Transition = { type: "spring", stiffness: 520, damping: 34, mass: 0.8 };

/** A little life for things the user just committed (a mark, a toggle). */
export const SPRING_POP: Transition = { type: "spring", stiffness: 500, damping: 22, mass: 0.7 };

/** Moving indicators (tab pill): critically damped, settles in ~200 ms. */
export const SPRING_SLIDE: Transition = { type: "spring", stiffness: 600, damping: 42 };

export const EASE_OUT = [0.22, 1, 0.36, 1] as const;

/**
 * HeroUI modal: keeps its CSS variables (scale / slide differ per size and placement) but swaps the slow
 * 400-600 ms defaults for a 200 ms enter and a 150 ms exit along the same path (apple-design: symmetric).
 */
export const modalMotion = {
  variants: {
    enter: {
      scale: "var(--scale-enter)",
      y: "var(--slide-enter)",
      opacity: 1,
      willChange: "auto",
      transition: {
        scale: { duration: 0.2, ease: EASE_OUT },
        opacity: { duration: 0.18, ease: "easeOut" },
        y: { type: "spring", bounce: 0, duration: 0.3 },
      },
    },
    exit: {
      scale: "var(--scale-exit)",
      y: "var(--slide-exit)",
      opacity: 0,
      willChange: "transform",
      transition: { duration: 0.15, ease: "easeIn" },
    },
  },
} as const;

/**
 * Phone bottom sheet (AppModal): rises from the bottom edge and leaves the same way (apple-design: symmetric
 * paths), critically damped spring in, 220 ms ease out. Under reduced motion `overlayFade` is used instead.
 */
export const sheetMotion = {
  variants: {
    enter: { y: 0, opacity: 1, transition: { type: "spring", bounce: 0, duration: 0.38 } },
    exit: { y: "100%", opacity: 1, transition: { duration: 0.22, ease: [0.4, 0, 1, 1] } },
  },
} as const;

/**
 * Any HeroUI overlay under reduced motion (modal, drawer, popover / dropdown / select, tooltip): opacity only,
 * no scale and no slide. Covers every variant name HeroUI uses (`initial` for popovers, `exit` as the start
 * for modals, drawers and tooltips).
 */
export const overlayFade = {
  variants: {
    initial: { opacity: 0, scale: 1, x: 0, y: 0 },
    enter: { opacity: 1, scale: 1, x: 0, y: 0, transition: { duration: 0.12 } },
    exit: { opacity: 0, scale: 1, x: 0, y: 0, transition: { duration: 0.1 } },
  },
} as const;

/** motionProps for a HeroUI Drawer / Dropdown / Tooltip / Select popover: the default motion, or a fade under reduced motion. */
export function useOverlayMotion() {
  return useReducedMotion() ? overlayFade : undefined;
}
