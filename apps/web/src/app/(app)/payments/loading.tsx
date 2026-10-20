import { StatCardsSkeleton } from "@/components/StatCards";
import { Bone, HeaderSkeleton, Late, ListSkeleton } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <HeaderSkeleton action />
      <StatCardsSkeleton count={3} />
      <Bone className="mb-4 h-10 w-56 rounded-xl" />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Bone className="h-10 flex-1 rounded-xl md:max-w-xs md:flex-none md:basis-80" />
        <Bone className="hidden h-14 w-44 rounded-xl md:block" />
      </div>
      <ListSkeleton cols={8} />
    </Late>
  );
}
