"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { CertCatalog, CertSettings, TemplateDetail, TemplateListItem, TemplateRule } from "@/lib/cert-editor/types";
import { can } from "@/lib/permissions";
import { useMe } from "./queries";

export const CERT_TEMPLATES_KEY = ["cert-templates"] as const;
export const CERT_SETTINGS_KEY = ["cert-settings"] as const;

export function useTemplates() {
  return useQuery({
    queryKey: CERT_TEMPLATES_KEY,
    queryFn: () => api<{ items: TemplateListItem[] }>("/api/v1/cert-templates"),
  });
}

export function useTemplate(id: string) {
  return useQuery({
    queryKey: ["cert-template", id],
    queryFn: () => api<TemplateDetail>(`/api/v1/cert-templates/${id}`),
    staleTime: 0,
    gcTime: 0,
  });
}

export function useCertCatalog() {
  return useQuery({ queryKey: ["cert-fields"], queryFn: () => api<CertCatalog>("/api/v1/cert-fields"), staleTime: Infinity });
}

export function useCertSettings() {
  return useQuery({ queryKey: CERT_SETTINGS_KEY, queryFn: () => api<CertSettings>("/api/v1/cert-settings") });
}

export function useCertRules() {
  return useQuery({
    queryKey: ["cert-rules"],
    queryFn: () => api<{ rules: TemplateRule[] }>("/api/v1/cert-template-rules"),
  });
}

export function useCanChangeCerts(): boolean {
  const { data: me } = useMe();

  return !!me && can(me.permissions, "cert_templates", "change");
}

export function useRefreshCerts() {
  const qc = useQueryClient();

  return () => qc.invalidateQueries({ queryKey: CERT_TEMPLATES_KEY });
}

/** Multipart upload through the same CSRF-aware path as `api()` (which sends JSON only). */
export async function uploadForm<T>(
  path: string,
  file: Blob,
  fileName: string,
  opts: { query?: Record<string, string>; fields?: Record<string, string> } = {},
): Promise<T> {
  const form = new FormData();

  form.append("file", file, fileName);
  for (const [k, v] of Object.entries(opts.fields ?? {})) form.append(k, v);
  const query = new URLSearchParams(opts.query ?? {}).toString();
  const response = await fetch(query ? `${path}?${query}` : path, {
    method: "POST",
    headers: { "X-Requested-With": "ilm" },
    body: form,
    credentials: "same-origin",
  });

  if (!response.ok) {
    const data = await response.json().catch(() => null);

    throw { status: response.status, code: data?.code ?? "internal_error", params: data?.params };
  }
  if (response.headers.get("content-type")?.includes("application/json")) return (await response.json()) as T;

  return (await response.blob()) as T;
}

export async function postForPdf(path: string, body: unknown): Promise<Blob> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "X-Requested-With": "ilm", "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "same-origin",
  });

  if (!response.ok) {
    const data = await response.json().catch(() => null);

    throw { status: response.status, code: data?.code ?? "internal_error", params: data?.params };
  }

  return response.blob();
}

export async function getFile(path: string): Promise<{ blob: Blob; name: string | null }> {
  const response = await fetch(path, { credentials: "same-origin" });

  if (!response.ok) {
    const data = await response.json().catch(() => null);

    throw { status: response.status, code: data?.code ?? "internal_error", params: data?.params };
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  const name = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition)?.[1] ?? null;

  return { blob: await response.blob(), name: name ? decodeURIComponent(name) : null };
}

export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");

  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export type GraduateCertTemplates = {
  default_template_id: string | null;
  templates: { id: string; name: string; lang: string }[];
};

export const graduateTemplatesPath = (enrollmentId: string) => `/api/v1/graduates/${enrollmentId}/certificate/templates`;
