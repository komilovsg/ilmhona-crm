/** Row number for people lists: a narrow «№» column on desktop, a muted «1.» before the name on phones. */
export const rowNo = (page: number, pageSize: number, i: number) => (page - 1) * pageSize + i + 1;

export function NoTh() {
  return <th className="w-10 px-2 py-3 text-center font-medium">№</th>;
}

export function NoTd({ n }: { n: number }) {
  return <td className="px-2 py-3 text-center text-xs tabular-nums text-default-500">{n}</td>;
}

export function NoPrefix({ n }: { n: number }) {
  return <span className="mr-2 text-xs font-normal tabular-nums text-default-500">{n}.</span>;
}
