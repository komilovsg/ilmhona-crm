// Shared motion presets (framer-motion, the library HeroUI already ships with; `motion` is its new name).
// Rules: 150-250 ms, springs where the thing is touched, transform + opacity only (no layout shift),
// and everything is switched to «no movement» by <MotionConfig reducedMotion="user"> in Providers.

import type { Transition, Variants } from "framer-motion";

/** Touch feedback and small state changes: quick, no overshoot. */
export const SPRING_SNAPPY: Transition = { type: "spring", stiffness: 520, damping: 34, mass: 0.8 };

/** A little life for things the user just committed (a mark, a toggle). */
export const SPRING_POP: Transition = { type: "spring", stiffness: 500, damping: 22, mass: 0.7 };

/** Moving indicators (tab pill): critically damped, settles in ~200 ms. */
export const SPRING_SLIDE: Transition = { type: "spring", stiffness: 600, damping: 42 };

export const EASE_OUT = [0.22, 1, 0.36, 1] as const;

/** Route change: the new page fades in and rises 6 px. */
export const pageVariants: Variants = {
  hidden: { opacity: 0, y: 6 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.2, ease: EASE_OUT } },
};

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

/** HeroUI toast: a short spring instead of the 300 ms ease. */
export const toastMotion = { transition: { type: "spring", duration: 0.28, bounce: 0.12 } } as const;
