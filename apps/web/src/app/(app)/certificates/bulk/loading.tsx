import { Bone, HeaderSkeleton, Late } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <HeaderSkeleton />
      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        {Array.from({ length: 2 }, (_, i) => (
          <Bone key={i} className="h-14 w-full rounded-xl" />
        ))}
      </div>
      <Bone className="h-40 w-full rounded-2xl" />
    </Late>
  );
}
