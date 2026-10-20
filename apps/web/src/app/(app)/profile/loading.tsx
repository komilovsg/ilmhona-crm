import { FormSkeleton, HeaderSkeleton, Late } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <HeaderSkeleton />
      <div className="grid gap-5 md:grid-cols-2">
        <FormSkeleton fields={4} />
        <FormSkeleton fields={3} />
      </div>
    </Late>
  );
}
