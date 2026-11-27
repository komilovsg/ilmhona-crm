import { IlmMark } from "./brand/IlmMark";

/** Wordmark: house mark + «ilmhona» + tagline; white on the dark brand surfaces, `tone` sets the colour elsewhere. */
export function Logo({
  tagline = true,
  className = "",
  tone = "text-white",
}: {
  tagline?: boolean;
  className?: string;
  tone?: string;
}) {
  return (
    <div aria-label="ilmhona" className={`flex items-center gap-3 leading-none ${tone} ${className}`} role="img">
      <IlmMark height={26} />
      <div>
        <div className="text-2xl font-bold tracking-tight">ilmhona</div>
        {tagline && <div className="mt-1 text-[11px] tracking-wide text-[#8B98A5]">skills accelerator</div>}
      </div>
    </div>
  );
}
