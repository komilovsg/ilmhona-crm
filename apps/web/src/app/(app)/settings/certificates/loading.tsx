import { Bone, CardGridSkeleton, Late } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <Bone className="mb-1 h-4 w-24" />
      <Bone className="mb-5 h-8 w-48" />
      <Bone className="mb-5 h-12 w-80 max-w-full" />
      <CardGridSkeleton cards={4} lines={3} />
    </Late>
  );
}
