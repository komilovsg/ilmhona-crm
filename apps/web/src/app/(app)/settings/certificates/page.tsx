import { redirect } from "next/navigation";

export default function CertificatesSettingsPage() {
  redirect("/certificates?tab=templates");
}
