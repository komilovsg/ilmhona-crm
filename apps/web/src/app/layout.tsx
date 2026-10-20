import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import Script from "next/script";

import { Providers } from "./providers";

import { themeInitScript } from "@/context/theme-init";
import "./globals.css";

// Self-hosted: next/font downloads the font at build time and serves it from our own origin.
const inter = Inter({ subsets: ["latin", "cyrillic"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: { default: "ilmhona CRM", template: "%s · ilmhona CRM" },
  // Private app behind a login: nothing to index.
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html suppressHydrationWarning className={inter.variable} lang="ru">
      <body className="bg-background text-foreground antialiased">
        <Script id="theme-init" strategy="beforeInteractive">
          {themeInitScript}
        </Script>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
