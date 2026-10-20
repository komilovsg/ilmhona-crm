// Not a client module: the root layout (server) imports the script string from here.

export const THEME_STORAGE_KEY = "ilm-theme";
export type ThemePreference = "light" | "dark" | "system";

/**
 * Puts the theme class on <html> before the first paint (inline in <head>), so the dark theme
 * does not flash light. "system" (or nothing stored) follows the OS.
 */
export const themeInitScript = `try{var p=localStorage.getItem("${THEME_STORAGE_KEY}");var t=p==="light"||p==="dark"?p:(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");document.documentElement.classList.add(t)}catch(e){document.documentElement.classList.add("light")}`;
