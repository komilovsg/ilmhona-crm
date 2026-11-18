import type { DirectorByLang } from "./types.ts";

export type DirectorValues = { name: string; title: string };

/** The director of a template language; an empty part falls back to the Russian one. */
export function directorFor(byLang: DirectorByLang | undefined, lang: string): DirectorValues | null {
  const ru = byLang?.ru;

  if (!ru) return null;
  const own = byLang[lang as keyof DirectorByLang];

  return { name: own?.name || ru.name, title: own?.title || ru.title };
}

/** Sample values with the director of the template language put over the fake one. */
export function withDirector(values: Record<string, string> | undefined, byLang: DirectorByLang | undefined, lang: string): Record<string, string> | undefined {
  const d = directorFor(byLang, lang);

  if (!values || !d) return values;

  return { ...values, "company.director_name": d.name, "company.director_title": d.title };
}
