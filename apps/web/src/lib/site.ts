import type { Metadata, Viewport } from "next";

export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://ilmhona-crm.vercel.app";
export const SITE_NAME = "ilmhona CRM";
export const SITE_DESCRIPTION = "Учёт студентов, потоков, посещаемости и оплат — ilmhona skills accelerator";

const IMAGE = { width: 1200, height: 630, alt: "ilmhona CRM — skills accelerator" };

/** Root metadata: link previews (Open Graph, Twitter) and noindex. Static text only, never data. */
export const siteMetadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: SITE_NAME, template: `%s · ${SITE_NAME}` },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  // Private app behind a login: nothing to index (X-Robots-Tag in next.config.ts says the same).
  robots: { index: false, follow: false },
  openGraph: {
    type: "website",
    locale: "ru_RU",
    siteName: SITE_NAME,
    url: "/",
    title: SITE_NAME,
    description: SITE_DESCRIPTION,
    images: [{ url: "/opengraph-image", ...IMAGE }],
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_NAME,
    description: SITE_DESCRIPTION,
    images: [{ url: "/twitter-image", ...IMAGE }],
  },
  appleWebApp: { capable: true, title: "ilmhona", statusBarStyle: "black-translucent" },
};

export const siteViewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // the page runs under the notch / home bar; fixed edges pad themselves with env(safe-area-inset-*)
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FFFFFF" },
    { media: "(prefers-color-scheme: dark)", color: "#0F151B" },
  ],
};

/** The login page is what a shared link opens: same card, its own url (nested openGraph replaces the root one whole). */
export const loginMetadata: Metadata = {
  title: { absolute: SITE_NAME },
  description: SITE_DESCRIPTION,
  openGraph: { ...siteMetadata.openGraph, url: "/login" },
  twitter: siteMetadata.twitter,
};
