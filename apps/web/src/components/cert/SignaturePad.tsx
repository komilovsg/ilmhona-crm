"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@heroui/button";

import { AppModal } from "@/components/AppModal";
import { cropBox, strokeSegments, type Pt } from "@/lib/cert-editor/signature";

const W = 1200;
const H = 480;
const LINE = 7;

function paint(ctx: CanvasRenderingContext2D, strokes: Pt[][]) {
  ctx.clearRect(0, 0, W, H);
  ctx.strokeStyle = "#111111";
  ctx.fillStyle = "#111111";
  ctx.lineWidth = LINE;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const stroke of strokes) {
    ctx.beginPath();
    for (const s of strokeSegments(stroke)) {
      if (s.kind === "dot") {
        ctx.arc(s.to.x, s.to.y, LINE / 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
      } else if (s.kind === "move") ctx.moveTo(s.to.x, s.to.y);
      else if (s.kind === "quad") ctx.quadraticCurveTo(s.ctrl.x, s.ctrl.y, s.to.x, s.to.y);
      else ctx.lineTo(s.to.x, s.to.y);
    }
    ctx.stroke();
  }
}

/** Draw a signature with a finger or a mouse; «Готово» hands over a transparent PNG (2x the pad's 600x240). */
export function SignaturePadModal({ onClose, onDone }: { onClose: () => void; onDone: (png: Blob) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const strokes = useRef<Pt[][]>([]);
  const drawing = useRef(false);
  const [count, setCount] = useState(0);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");

    if (ctx) paint(ctx, strokes.current);
  }, [count]);

  const point = (e: React.PointerEvent<HTMLCanvasElement>): Pt => {
    const r = e.currentTarget.getBoundingClientRect();

    return { x: ((e.clientX - r.left) * W) / r.width, y: ((e.clientY - r.top) * H) / r.height };
  };
  const redraw = () => {
    const ctx = canvas.current?.getContext("2d");

    if (ctx) paint(ctx, strokes.current);
  };

  function finish() {
    const box = cropBox(strokes.current, LINE * 3, W, H);
    const src = canvas.current;

    if (!box || !src) return;
    const out = document.createElement("canvas");

    out.width = Math.ceil(box.w);
    out.height = Math.ceil(box.h);
    out.getContext("2d")?.drawImage(src, box.x, box.y, box.w, box.h, 0, 0, box.w, box.h);
    out.toBlob((b) => b && onDone(b), "image/png");
  }

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <Button
            isDisabled={count === 0}
            variant="flat"
            onPress={() => {
              strokes.current = [];
              setCount(0);
            }}
          >
            Очистить
          </Button>
          <Button color="primary" isDisabled={count === 0} onPress={finish}>
            Готово
          </Button>
        </>
      }
      guard={false}
      isOpen
      size="2xl"
      title="Нарисуйте подпись"
      onClose={onClose}
    >
      <p className="mb-2 text-sm text-default-500">Рисуйте пальцем или мышью. Фон будет прозрачным.</p>
      <canvas
        ref={canvas}
        aria-label="Поле для подписи"
        className="aspect-[5/2] w-full cursor-crosshair touch-none rounded-xl border border-divider bg-white"
        data-testid="signature-pad"
        height={H}
        width={W}
        onPointerCancel={() => (drawing.current = false)}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          drawing.current = true;
          strokes.current.push([point(e)]);
          redraw();
          setCount(strokes.current.length);
        }}
        onPointerMove={(e) => {
          if (!drawing.current) return;
          strokes.current.at(-1)?.push(point(e));
          redraw();
        }}
        onPointerUp={() => (drawing.current = false)}
      />
    </AppModal>
  );
}
