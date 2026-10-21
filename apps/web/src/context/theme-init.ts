// Not a client module: the root layout (server) imports the script string from here.

export const THEME_STORAGE_KEY = "ilm-theme";
export const SIDEBAR_STORAGE_KEY = "ilm-sidebar";
export type ThemePreference = "light" | "dark" | "system";

/**
 * Puts the theme class and the sidebar state on <html> before the first paint (inline in <head>), so the
 * dark theme does not flash light and the collapsed sidebar does not jump open. "system" (or nothing
 * stored) follows the OS. CSS reads `html[data-sidebar="collapsed"]`.
 */
export const themeInitScript = `try{var p=localStorage.getItem("${THEME_STORAGE_KEY}");var t=p==="light"||p==="dark"?p:(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");document.documentElement.classList.add(t)}catch(e){document.documentElement.classList.add("light")}try{if(localStorage.getItem("${SIDEBAR_STORAGE_KEY}")==="collapsed")document.documentElement.dataset.sidebar="collapsed"}catch(e){}`;
