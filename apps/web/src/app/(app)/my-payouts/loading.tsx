import { StatCardsSkeleton } from "@/components/StatCards";
import { Bone, HeaderSkeleton, Late, ListSkeleton } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <HeaderSkeleton />
      <StatCardsSkeleton count={4} />
      <Bone className="mb-4 h-10 w-56 rounded-xl" />
      <ListSkeleton cols={6} />
    </Late>
  );
}
