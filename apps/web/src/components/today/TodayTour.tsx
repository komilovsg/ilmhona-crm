"use client";

import { useEffect } from "react";
import { driver, type DriveStep } from "driver.js";
import "driver.js/dist/driver.css";

import { markTourSeen, tourSeen } from "@/lib/tour";

const STEPS: DriveStep[] = [
  {
    popover: {
      title: "Это ваш день",
      description: "Здесь уроки на сегодня, а под ними — что ещё не отмечено. Покажем за минуту, как это устроено.",
    },
  },
  {
    element: '[data-tour="focus"]',
    popover: {
      title: "Текущий или следующий урок",
      description: "Он выделен рамкой и стоит в расписании первым делом: время, поток, аудитория и сколько студентов.",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="mark"]',
    popover: {
      title: "Отметить посещаемость",
      description: "Одна кнопка у каждого урока. Она открывает список студентов, где можно отметить всех сразу.",
      side: "top",
    },
  },
  {
    element: '[data-tour="timeline"]',
    popover: {
      title: "Расписание по времени",
      description: "Прошедшие уроки светлее, будущие ниже. Если уроков нет, здесь будет дата следующего.",
      side: "top",
    },
  },
  {
    element: '[data-tour="undone"]',
    popover: {
      title: "Что осталось сделать",
      description: "Прошедшие уроки, где отмечены не все студенты. Нажмите на урок, чтобы дозаполнить.",
      side: "top",
    },
  },
  {
    popover: {
      title: "Подсказки всегда под рукой",
      description: "Показать этот тур снова можно в разделе «Профиль», кнопка «Показать подсказки».",
    },
  },
];

/** Steps whose target is on the screen (a step with no element is a centred card). */
function visibleSteps(): DriveStep[] {
  return STEPS.filter((s) => {
    if (typeof s.element !== "string") return true;
    const el = document.querySelector<HTMLElement>(s.element);

    return !!el && el.getClientRects().length > 0;
  });
}

/**
 * First-visit tour of «Сегодня» for an instructor: shown once per user (browser storage), «Пропустить»
 * on every step, motion off under prefers-reduced-motion. Colours come from the theme (globals.css).
 */
export function TodayTour({ userId }: { userId: string }) {
  useEffect(() => {
    if (tourSeen(userId)) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let tour: ReturnType<typeof driver> | undefined;
    // let the schedule paint first; the target elements must exist
    const timer = window.setTimeout(() => {
      const steps = visibleSteps();
      if (steps.length === 0) return;
      tour = driver({
        steps,
        animate: !reduce,
        smoothScroll: !reduce,
        overlayOpacity: 0.6,
        stagePadding: 6,
        stageRadius: 16,
        popoverClass: "ilm-tour",
        showProgress: true,
        progressText: "{{current}} из {{total}}",
        nextBtnText: "Далее",
        prevBtnText: "Назад",
        doneBtnText: "Готово",
        closeBtnLabel: "Закрыть",
        onPopoverRender: (popover) => {
          const skip = document.createElement("button");
          skip.type = "button";
          skip.className = "ilm-tour-skip";
          skip.textContent = "Пропустить";
          skip.addEventListener("click", () => tour?.destroy());
          popover.footer.insertBefore(skip, popover.footerButtons);
        },
        onDestroyed: () => markTourSeen(userId),
      });
      tour.drive();
    }, 600);

    return () => {
      window.clearTimeout(timer);
      tour?.destroy();
    };
  }, [userId]);

  return null;
}
