// Who pays for a cohort's students (pure: unit-tested with node --test).

export type FundingKind = "платный" | "бесплатный" | "донор" | "смешанный";

export const FUNDINGS: { key: FundingKind; label: string }[] = [
  { key: "платный", label: "Платный" },
  { key: "бесплатный", label: "Бесплатный" },
  { key: "донор", label: "За счёт донора" },
  { key: "смешанный", label: "Смешанный" },
];

/** «донор» needs donors, «смешанный» may have them; «платный» and «бесплатный» take none. */
export function withDonors(funding: string): boolean {
  return funding === "донор" || funding === "смешанный";
}

export function fundingLabel(funding: string): string {
  return FUNDINGS.find((f) => f.key === funding)?.label ?? funding;
}

/** How one student is paid for: «Донор: X», «Бесплатно», «Платит сам». */
export function studentFunding(funding: string, donorId: string | null, donors: { id: string; name: string }[]): string {
  if (donorId) return `Донор: ${donors.find((d) => d.id === donorId)?.name ?? "—"}`;

  return funding === "бесплатный" ? "Бесплатно" : "Платит сам";
}

/** The form's problem with the chosen funding, or null. */
export function fundingProblem(funding: string, donorIds: string[]): string | null {
  if (funding === "донор" && donorIds.length === 0) return "Выберите хотя бы одного донора";

  return null;
}
