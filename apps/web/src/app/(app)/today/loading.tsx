import { Bone, HeaderSkeleton, Late } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <HeaderSkeleton />
      <div className="mb-6 grid gap-3 md:grid-cols-2">
        {[0, 1].map((i) => (
          <Bone key={i} className="h-28 w-full rounded-2xl" />
        ))}
      </div>
    </Late>
  );
}
