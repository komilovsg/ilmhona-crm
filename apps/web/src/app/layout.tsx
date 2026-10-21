import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { Inter } from "next/font/google";

import { Providers } from "./providers";

import { themeInitScript } from "@/context/theme-init";
import { siteMetadata, siteViewport } from "@/lib/site";
import "./globals.css";

// Self-hosted: next/font downloads the font at build time and serves it from our own origin.
const inter = Inter({ subsets: ["latin", "cyrillic"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = siteMetadata;

export const viewport: Viewport = siteViewport;

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // The CSP nonce set per request in proxy.ts; the inline theme script must carry it to run.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html suppressHydrationWarning className={inter.variable} lang="ru">
      <head>
        {/* A real inline script in <head> (next/script's beforeInteractive runs only at bootstrap, after the first paint):
            theme class and sidebar state are on <html> before anything is painted. */}
        <script suppressHydrationWarning dangerouslySetInnerHTML={{ __html: themeInitScript }} nonce={nonce} />
      </head>
      <body className="bg-background text-foreground antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
