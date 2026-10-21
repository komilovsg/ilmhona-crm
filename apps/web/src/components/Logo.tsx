import { IlmMark } from "./brand/IlmMark";

/** Wordmark: house mark + «ilmhona» + tagline, white on the dark brand surfaces. */
export function Logo({ tagline = true, className = "" }: { tagline?: boolean; className?: string }) {
  return (
    <div aria-label="ilmhona" className={`flex items-center gap-3 leading-none text-white ${className}`} role="img">
      <IlmMark height={26} />
      <div>
        <div className="text-2xl font-bold tracking-tight">ilmhona</div>
        {tagline && <div className="mt-1 text-[11px] tracking-wide text-[#8B98A5]">skills accelerator</div>}
      </div>
    </div>
  );
}
