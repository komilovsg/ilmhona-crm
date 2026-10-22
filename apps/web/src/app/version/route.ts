// The commit this web build was made from: the deploy-api workflow compares it with the API's.
// Public and secret-free (src/proxy.ts PUBLIC_PATHS).
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ sha: process.env.VERCEL_GIT_COMMIT_SHA ?? "dev" }, { headers: { "cache-control": "no-store" } });
}
