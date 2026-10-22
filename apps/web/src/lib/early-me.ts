// Not a client-only module: the root layout (server) imports the script string from here.

/**
 * Starts GET /api/v1/auth/me while the HTML is still being parsed (inline in <head>), so the answer is
 * already on its way when the JavaScript has downloaded and hydrated; the app shell shows nothing real
 * until it knows the user. Skipped on the public pages. `useMe` takes the promise once (`takeEarlyMe`);
 * anything but a 200 falls back to the normal `api()` call (refresh, redirects, error texts).
 */
export const earlyMeScript = `try{if(!/^\\/(login|forgot-password)(\\/|$)/.test(location.pathname))window.__ilmMe=fetch("/api/v1/auth/me",{credentials:"same-origin"}).catch(function(){})}catch(e){}`;

declare global {
  interface Window {
    __ilmMe?: Promise<Response | void>;
  }
}

/** The response of the early request (once), or null when there is none or it failed. */
export async function takeEarlyMe(): Promise<unknown> {
  const early = typeof window === "undefined" ? undefined : window.__ilmMe;

  if (!early) return null;
  window.__ilmMe = undefined;
  const response = await early;

  return response && response.ok ? response.json().catch(() => null) : null;
}
