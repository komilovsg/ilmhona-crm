import { Bone, Late } from "@/components/Skeletons";

export default function Loading() {
  return (
    <Late>
      <Bone className="mb-4 h-5 w-24" />
      <Bone className="mb-2 h-7 w-2/3" />
      <Bone className="mb-5 h-5 w-1/2" />
      {[0, 1, 2, 3, 4].map((i) => (
        <Bone key={i} className="mb-2 h-[88px] w-full rounded-2xl" />
      ))}
    </Late>
  );
}
