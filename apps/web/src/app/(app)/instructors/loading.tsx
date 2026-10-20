import { Bone, CardGridSkeleton, HeaderSkeleton, Late } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <HeaderSkeleton />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Bone className="h-10 flex-1 rounded-xl md:max-w-xs md:flex-none md:basis-80" />
      </div>
      <CardGridSkeleton cards={6} />
    </Late>
  );
}
