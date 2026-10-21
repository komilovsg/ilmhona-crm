import { StatCardsSkeleton } from "@/components/StatCards";
import { Bone, HeaderSkeleton, Late } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <HeaderSkeleton />
      <Bone className="mb-4 h-11 w-72 rounded-xl" />
      <StatCardsSkeleton count={3} />
      <StatCardsSkeleton count={3} />
      <StatCardsSkeleton count={3} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Bone className="h-72 w-full rounded-2xl" />
        <Bone className="h-72 w-full rounded-2xl" />
      </div>
    </Late>
  );
}
