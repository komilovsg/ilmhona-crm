import { Bone, HeaderSkeleton, Late } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <HeaderSkeleton action />
      <div className="grid items-start gap-5 md:grid-cols-[18rem_1fr]">
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Bone key={i} className="h-12 w-full rounded-xl" />
          ))}
        </div>
        <Bone className="h-96 w-full rounded-2xl" />
      </div>
    </Late>
  );
}
