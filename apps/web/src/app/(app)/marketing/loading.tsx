import { StatCardsSkeleton } from "@/components/StatCards";
import { Bone, HeaderSkeleton, Late, ListSkeleton } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <HeaderSkeleton action />
      <StatCardsSkeleton count={4} />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Bone key={i} className="h-14 w-full rounded-xl" />
        ))}
      </div>
      <Bone className="mb-5 h-56 w-full rounded-2xl" />
      <ListSkeleton cols={9} />
    </Late>
  );
}
