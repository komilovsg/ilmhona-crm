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

/** «Не платит» is a mark of the cohorts where students pay: «платный» and «смешанный». */
export function priced(funding: string): boolean {
  return funding === "платный" || funding === "смешанный";
}

export const NOT_PAYING = "__not_paying__";
export const NOT_PAYING_LABEL = "Не платит";

/** The choices of who pays for one student besides «Платит сам» (null): «Не платит» and the donors. */
export function payerOptions(funding: string, donors: { id: string; name: string }[]): { key: string; label: string }[] {
  return [
    ...(priced(funding) ? [{ key: NOT_PAYING, label: NOT_PAYING_LABEL }] : []),
    ...(withDonors(funding) ? donors.map((d) => ({ key: d.id, label: funding === "донор" ? d.name : `Донор: ${d.name}` })) : []),
  ];
}

/** The chosen payer (null = «Платит сам») as request fields. */
export function payerBody(key: string | null): { donor_id: string | null; not_paying: boolean } {
  return { donor_id: key === NOT_PAYING ? null : key, not_paying: key === NOT_PAYING };
}

/** The payer choice of an enrollment (null = «Платит сам»). */
export function payerKey(donorId: string | null, notPaying: boolean): string | null {
  return notPaying ? NOT_PAYING : donorId;
}

export function fundingLabel(funding: string): string {
  return FUNDINGS.find((f) => f.key === funding)?.label ?? funding;
}

/** How one student is paid for: «Донор: X», «Не платит», «Бесплатно», «Платит сам». */
export function studentFunding(
  funding: string,
  donorId: string | null,
  donors: { id: string; name: string }[],
  notPaying = false,
): string {
  if (notPaying) return NOT_PAYING_LABEL;
  if (donorId) return `Донор: ${donors.find((d) => d.id === donorId)?.name ?? "—"}`;

  return funding === "бесплатный" ? "Бесплатно" : "Платит сам";
}

/** The form's problem with the chosen funding, or null. */
export function fundingProblem(funding: string, donorIds: string[]): string | null {
  if (funding === "донор" && donorIds.length === 0) return "Выберите хотя бы одного донора";

  return null;
}
