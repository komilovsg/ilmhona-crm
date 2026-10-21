import { Bone, HeaderSkeleton, Late, ListSkeleton } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <HeaderSkeleton action />
      <Bone className="mb-4 h-11 w-60 rounded-xl" />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Bone key={i} className="h-14 w-full rounded-xl" />
        ))}
      </div>
      <ListSkeleton cols={8} />
    </Late>
  );
}
