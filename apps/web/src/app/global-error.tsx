"use client";

import { ILM_MARK_PATH } from "@/components/brand/IlmMark";
import { ERROR_COPY, supportCode } from "@/lib/error-copy";

const copy = ERROR_COPY.fatal;

// Own document (the root layout is gone), so no Tailwind/HeroUI: a few plain rules. A <style> element
// and style attributes are allowed by the CSP (style-src 'unsafe-inline'); no script of our own.
const CSS = `
:root{color-scheme:light dark;--bg:#f5f7f9;--fg:#151a1e;--muted:#5b6670;--brand:#006b99;--btn:#006b99;--btn-fg:#fff;--line:#d6dde3}
@media (prefers-color-scheme:dark){:root{--bg:#0a0f14;--fg:#e6edf3;--muted:#9aa7b3;--brand:#38bdf0;--btn:#38bdf0;--btn-fg:#06141c;--line:#2a3540}}
body{margin:0;min-height:100dvh;display:flex;align-items:center;justify-content:center;background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{box-sizing:border-box;max-width:28rem;padding:2rem 1rem;text-align:center}
h1{margin:1rem 0 .5rem;font-size:1.375rem}
p{margin:0;color:var(--muted);font-size:.875rem;line-height:1.5}
.row{display:flex;flex-wrap:wrap;justify-content:center;gap:.75rem;margin-top:1.5rem}
.btn{display:inline-block;box-sizing:border-box;min-height:2.5rem;padding:.625rem 1.25rem;border-radius:.75rem;border:1px solid var(--line);background:transparent;color:var(--fg);font:inherit;font-size:.875rem;text-decoration:none;cursor:pointer}
.btn.primary{background:var(--btn);border-color:var(--btn);color:var(--btn-fg)}
.code{margin-top:1.5rem;font-size:.75rem}
@media (prefers-reduced-motion:no-preference){main{animation:in .25s ease-out}@keyframes in{from{opacity:0;transform:translateY(6px)}}}
`;

/** The root layout itself failed: a self-contained Russian page with its own <html>/<body>. */
export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  const code = supportCode(error);

  return (
    <html lang="ru">
      <body>
        <title>{copy.title}</title>
        <style>{CSS}</style>
        <main role="alert">
          <svg aria-hidden="true" fill="none" height="40" style={{ color: "var(--brand)" }} viewBox="0 0 960 754" width="51">
            <path d={ILM_MARK_PATH} fill="currentColor" />
          </svg>
          <h1>{copy.title}</h1>
          <p>{copy.text}</p>
          <div className="row">
            <button className="btn primary" type="button" onClick={() => window.location.reload()}>
              {copy.retry}
            </button>
            {/* a plain link on purpose: a full reload leaves the broken tree */}
            <a className="btn" href="/">
              {copy.home}
            </a>
          </div>
          {code && (
            <p className="code">
              {copy.codeLabel}: <code>{code}</code>
            </p>
          )}
        </main>
      </body>
    </html>
  );
}
