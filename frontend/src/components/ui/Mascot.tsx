import React from "react";
import { cn } from "./utils";

/*
 * The snow leopard cub (docs/mascot/mascot_sheet.png, cut by scripts/mascot_crop.py). Always decorative: empty alt text,
 * so screen readers skip it. These are concept images: an illustrator's `public/mascot/<pose>.svg` replaces a pose at the
 * next build, no code change (next.config.ts lists the SVG files). Never use it inside the exam player.
 */
export type MascotPose = "hello" | "reading" | "thinking" | "celebrating" | "working" | "encouraging";

/** width / height of the current images, so the browser reserves the space before they load. */
const RATIO: Record<MascotPose, number> = {
  hello: 415 / 400,
  reading: 378 / 400,
  thinking: 334 / 400,
  celebrating: 405 / 400,
  working: 415 / 400,
  encouraging: 396 / 400,
};

const SVG_POSES = (process.env.NEXT_PUBLIC_MASCOT_SVG ?? "").split(",");

export interface MascotProps {
  pose: MascotPose;
  /** Height in px at most (the images are 400 px tall). Tailwind height classes in `className` may override it per breakpoint. */
  size?: number;
  /** The first thing on the page (landing hero): load it at once instead of lazily. */
  eager?: boolean;
  className?: string;
}

export function Mascot({ pose, size = 96, eager = false, className }: MascotProps) {
  const img = {
    alt: "",
    width: Math.round(size * RATIO[pose]),
    height: size,
    loading: eager ? "eager" : "lazy",
    decoding: "async",
    draggable: false,
    className: cn("shrink-0 select-none", className),
  } as const;
  if (SVG_POSES.includes(pose)) return <img src={`/mascot/${pose}.svg`} {...img} />;
  return (
    <picture className="contents">
      <source srcSet={`/mascot/${pose}.webp`} type="image/webp" />
      <img src={`/mascot/${pose}.png`} {...img} />
    </picture>
  );
}
