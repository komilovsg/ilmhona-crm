import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "ilmhona CRM",
    short_name: "ilmhona",
    description: "Учёт студентов, потоков, посещаемости и оплат — ilmhona skills accelerator",
    // The app sends each role to its own home (instructors to /today).
    start_url: "/today?source=pwa",
    scope: "/",
    display: "standalone",
    lang: "ru",
    background_color: "#101820",
    theme_color: "#101820",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
