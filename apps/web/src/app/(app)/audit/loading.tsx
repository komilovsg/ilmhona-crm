import { ListPageSkeleton } from "@/components/Skeletons";

export default function Loading() {
  return <ListPageSkeleton action={false} cols={4} />;
}
