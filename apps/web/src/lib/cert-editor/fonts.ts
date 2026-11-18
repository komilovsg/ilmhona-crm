import type { CertFont } from "./types.ts";

/** File of the API font route: `Montserrat-700Italic.ttf`. */
export function fontFile(family: string, weight: number, italic: boolean): string {
  return `${family.replace(/\s+/g, "")}-${weight}${italic ? "Italic" : ""}.ttf`;
}

export function fontFaceCss(fonts: CertFont[], base = "/api/v1/cert-fonts"): string {
  const rules: string[] = [];

  for (const f of fonts) {
    for (const [italic, weights] of [[false, f.weights], [true, f.italic_weights]] as const) {
      for (const w of weights) {
        rules.push(
          `@font-face{font-family:"${f.family}";font-weight:${w};font-style:${italic ? "italic" : "normal"};font-display:swap;src:url("${base}/${fontFile(f.family, w, italic)}") format("truetype")}`,
        );
      }
    }
  }

  return rules.join("\n");
}

/** The bundled weight nearest to the request (the CSS font matching does the same). */
export function nearestWeight(font: CertFont | undefined, weight: number, italic: boolean): { weight: number; italic: boolean } {
  if (!font) return { weight, italic };
  const useItalic = italic && font.italic_weights.length > 0;
  const set = useItalic ? font.italic_weights : font.weights;

  if (!set.length) return { weight, italic: useItalic };

  return { weight: set.reduce((a, b) => (Math.abs(b - weight) < Math.abs(a - weight) ? b : a)), italic: useItalic };
}
