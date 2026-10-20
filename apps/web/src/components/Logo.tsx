/** Text logo: "ilm" white + "hona" brand blue, tagline under it. For the dark sidebar and the login card. */
export function Logo({ tagline = true, className = "" }: { tagline?: boolean; className?: string }) {
  return (
    <div className={`leading-none ${className}`}>
      <div className="text-2xl font-bold tracking-tight">
        <span className="text-white">ilm</span>
        <span className="text-[#00A0DC]">hona</span>
      </div>
      {tagline && <div className="mt-1 text-[11px] tracking-wide text-[#8B98A5]">skills accelerator</div>}
    </div>
  );
}
