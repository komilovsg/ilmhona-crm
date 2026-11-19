/** Font sizes (pt) tried by the shrink-to-fit preview: size, size - 0.5, ... down to `min`. */
export function fitSteps(size: number, min: number | null): number[] {
  const floor = min !== null && min > 0 && min < size ? min : size;
  const out: number[] = [];

  for (let s = size; s > floor + 1e-9; s -= 0.5) out.push(Math.round(s * 100) / 100);
  out.push(floor);

  return out;
}

/** The first size for which `fits` is true, else the minimum with `overflow`. */
export function pickFit(steps: number[], fits: (pt: number) => boolean): { pt: number; overflow: boolean } {
  for (const pt of steps) if (fits(pt)) return { pt, overflow: false };

  return { pt: steps[steps.length - 1], overflow: true };
}
