import { Bone } from "@/components/Skeletons";

/** The default (superadmin) layout's first screen: banner, the month sentence, then two rows of cards. Server-safe. */
export function DashPageSkeleton({ manager = false }: { manager?: boolean }) {
  if (manager)
    return (
      <div className="grid gap-4 md:gap-6">
        <Bone className="h-[4.875rem] w-full rounded-2xl md:h-14" />
        <Bone className="h-[17.25rem] w-full rounded-[1.125rem] lg:h-[8.25rem]" />
        <div className="grid gap-4 md:gap-6 lg:grid-cols-5">
          <Bone className="h-[11.5rem] w-full rounded-2xl lg:col-span-3" />
          <Bone className="h-[9rem] w-full rounded-2xl lg:col-span-2" />
        </div>
        <Bone className="h-[7.5rem] w-full rounded-2xl lg:h-16" />
      </div>
    );

  return (
    <div className="grid gap-4 md:gap-6">
      <Bone className="h-[4.875rem] w-full rounded-2xl md:h-14" />
      <Bone className="h-[15rem] w-full rounded-2xl md:h-[11.25rem]" />
      <div className="grid gap-4 md:gap-6 lg:grid-cols-5">
        <Bone className="h-[14.75rem] w-full rounded-2xl lg:col-span-3 lg:h-[13.5rem]" />
        <Bone className="h-[22rem] w-full rounded-2xl lg:col-span-2" />
        <Bone className="h-[27rem] w-full rounded-2xl lg:col-span-3" />
        <Bone className="h-96 w-full rounded-2xl lg:col-span-2" />
      </div>
    </div>
  );
}
