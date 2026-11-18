// Sample dates in the constructor: the same three formats the API renders.

const RU = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split(" ");
const EN = "January February March April May June July August September October November December".split(" ");

export function formatDate(iso: string, format: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);

  if (!m) return iso;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];

  if (format === "d month yyyy") return `${d} ${RU[mo - 1]} ${y}`;
  if (format === "month d, yyyy") return `${EN[mo - 1]} ${d}, ${y}`;

  return `${String(d).padStart(2, "0")}.${String(mo).padStart(2, "0")}.${y}`;
}
