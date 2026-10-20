import { DetailSkeleton, Late } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <DetailSkeleton cells={0} />
    </Late>
  );
}
