import dynamic from "next/dynamic";
import type { ComponentType } from "react";

const loaders = new Set<() => Promise<unknown>>();

/**
 * A modal / form loaded on demand. It never suspends the page (client only, nothing shown while the chunk
 * arrives: the list stays, the sheet appears when ready) and registers itself so a row menu or a button can
 * fetch the chunk before the click lands (`preloadModals`).
 */
export function lazyModal<P extends object>(load: () => Promise<ComponentType<P>>) {
  loaders.add(load);

  return dynamic(load, { ssr: false, loading: () => null });
}

/** Start loading every lazy modal of the modules on screen (called when a row menu opens). */
export function preloadModals() {
  loaders.forEach((load) => void load());
}
