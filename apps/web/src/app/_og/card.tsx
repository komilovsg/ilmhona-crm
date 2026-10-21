import { readFile } from "node:fs/promises";

import { ImageResponse } from "next/og";

import { ILM_MARK_PATH } from "@/components/brand/IlmMark";

export const OG_SIZE = { width: 1200, height: 630 };
export const OG_ALT = "ilmhona CRM — skills accelerator";

/** Static link-preview card: brand mark and text only, never any data. Fonts are bundled (Inter, Latin + Cyrillic subset). */
export async function ogCard(): Promise<ImageResponse> {
  const [bold, regular] = await Promise.all([
    readFile(new URL("./Inter-Bold.otf", import.meta.url)),
    readFile(new URL("./Inter-Regular.otf", import.meta.url)),
  ]);
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "0 96px",
          background: "radial-gradient(circle at 0% 0%, #2aa9cc 0%, #14303d 42%, #101820 85%)",
          fontFamily: "Inter",
        }}
      >
        <svg fill="#FFFFFF" height={150} viewBox="0 0 960 754" width={191}>
          <path d={ILM_MARK_PATH} />
        </svg>
        <div style={{ display: "flex", marginTop: 36, fontSize: 96, fontWeight: 700, letterSpacing: -2, lineHeight: 1, color: "#FFFFFF" }}>
          ilmhona
        </div>
        <div style={{ marginTop: 12, fontSize: 36, color: "#9FB3BF", letterSpacing: 2 }}>skills accelerator</div>
        <div style={{ marginTop: 48, fontSize: 36, color: "#FFFFFF", lineHeight: 1.3 }}>
          Учёт студентов, потоков, посещаемости и оплат
        </div>
      </div>
    ),
    {
      ...OG_SIZE,
      fonts: [
        { name: "Inter", data: regular, weight: 400, style: "normal" },
        { name: "Inter", data: bold, weight: 700, style: "normal" },
      ],
    },
  );
}
