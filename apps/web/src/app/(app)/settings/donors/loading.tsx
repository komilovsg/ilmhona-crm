import { Bone, Late, ListSkeleton } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <Bone className="mb-1 h-4 w-24" />
      <Bone className="mb-5 h-8 w-48" />
      <ListSkeleton cols={4} rows={5} />
    </Late>
  );
}
