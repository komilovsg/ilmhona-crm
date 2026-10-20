import { StatCardsSkeleton } from "@/components/StatCards";
import { Bone, HeaderSkeleton, Late, ListSkeleton } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <HeaderSkeleton />
      <StatCardsSkeleton count={4} />
      <Bone className="mb-4 h-10 w-72 rounded-xl" />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 md:flex md:flex-wrap">
        <Bone className="h-14 rounded-xl md:w-52" />
        <Bone className="h-14 rounded-xl md:w-56" />
        <Bone className="h-14 rounded-xl md:w-48" />
      </div>
      <ListSkeleton cols={8} />
    </Late>
  );
}
