import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import Script from "next/script";

import { Providers } from "./providers";

import { themeInitScript } from "@/context/theme-init";
import { siteMetadata, siteViewport } from "@/lib/site";
import "./globals.css";

// Self-hosted: next/font downloads the font at build time and serves it from our own origin.
const inter = Inter({ subsets: ["latin", "cyrillic"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = siteMetadata;

export const viewport: Viewport = siteViewport;

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
