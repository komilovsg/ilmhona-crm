import { Bone, Late, SchemeSkeleton } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <Bone className="mb-1 h-4 w-24" />
      <Bone className="mb-5 h-8 w-64" />
      <SchemeSkeleton />
    </Late>
  );
}
