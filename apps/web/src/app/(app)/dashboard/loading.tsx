import { DashPageSkeleton } from "@/components/dash/PageSkeleton";
import { Bone, Late } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <div className="mx-auto flex max-w-[80rem] flex-col gap-4 md:gap-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-1">
            <Bone className="h-4 w-48" />
            <Bone className="h-9 w-40" />
          </div>
          <Bone className="h-12 w-72 rounded-xl" />
        </div>
        <DashPageSkeleton />
      </div>
    </Late>
  );
}
