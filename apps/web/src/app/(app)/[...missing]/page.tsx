import { notFound } from "next/navigation";

/** Any deeper unknown path (/foo/bar) is a 404 inside the shell. */
export default function Missing() {
  notFound();
}
