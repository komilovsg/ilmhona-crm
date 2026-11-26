/** Which user has seen the «Сегодня» tour. Kept in the browser: a blocked or cleared storage just
 * shows the tour again, which is harmless. */
const key = (userId: string) => `ilm-tour-today:${userId}`;

export function tourSeen(userId: string): boolean {
  try {
    return window.localStorage.getItem(key(userId)) === "1";
  } catch {
    return true; // no storage: do not nag on every visit
  }
}

export function markTourSeen(userId: string): void {
  try {
    window.localStorage.setItem(key(userId), "1");
  } catch {
    /* private window: nothing to remember */
  }
}

export function resetTour(userId: string): void {
  try {
    window.localStorage.removeItem(key(userId));
  } catch {
    /* nothing stored, nothing to reset */
  }
}

/** Destroy handler for the tour: Skip, close and finish mark it seen; leaving the page mid-tour does not. */
export function tourEnd(userId: string) {
  let leaving = false;

  return {
    leave: () => {
      leaving = true;
    },
    onDestroyed: () => {
      if (!leaving) markTourSeen(userId);
    },
  };
}
