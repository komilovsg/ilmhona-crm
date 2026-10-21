import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Забыли пароль?", robots: { index: false, follow: false } };

export default function ForgotPasswordLayout({ children }: { children: ReactNode }) {
  return children;
}
