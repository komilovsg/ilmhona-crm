import { readFile } from "node:fs/promises";

import { ImageResponse } from "next/og";

export const OG_SIZE = { width: 1200, height: 630 };
export const OG_ALT = "ilmhona CRM — skills accelerator";

/** Static link-preview card: brand text only, never any data. Fonts are bundled (Inter, Latin + Cyrillic subset). */
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
          background: "#101820",
          fontFamily: "Inter",
        }}
      >
        <div style={{ display: "flex", fontSize: 168, fontWeight: 700, letterSpacing: -4, lineHeight: 1 }}>
          <span style={{ color: "#FFFFFF" }}>ilm</span>
          <span style={{ color: "#00A0DC" }}>hona</span>
        </div>
        <div style={{ marginTop: 16, fontSize: 40, color: "#8B98A5", letterSpacing: 2 }}>skills accelerator</div>
        <div style={{ marginTop: 56, fontSize: 36, color: "#FFFFFF", lineHeight: 1.3 }}>
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
