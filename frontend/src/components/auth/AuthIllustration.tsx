"use client";

import React, { useId } from "react";
import { Mascot, type MascotPose } from "@/components/ui/Mascot";

/*
 * Decorative calm mountain scene for the auth screens (AUTH_SOCIAL_DESIGN 8.2): simple shapes in the student palette
 * (STUDENT_UI_DESIGN 1.1) and the snow leopard on the ground band. Nothing in it is read by screen readers.
 */

function Scene({ prefix, viewBox }: { prefix: string; viewBox: string }) {
  const sky = `${prefix}-sky`;
  const near = `${prefix}-near`;
  return (
    <svg aria-hidden="true" focusable="false" viewBox={viewBox} preserveAspectRatio="xMidYMax slice" className="absolute inset-0 h-full w-full">
      <defs>
        <linearGradient id={sky} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#DFF1FF" />
          <stop offset="1" stopColor="#F5FBFF" />
        </linearGradient>
        <linearGradient id={near} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#13698F" />
          <stop offset="1" stopColor="#0E4A6B" />
        </linearGradient>
      </defs>
      {/* the scene is 800 x 1000; the phone band shows the peaks (y 450-750) */}
      <rect width="800" height="1000" fill={`url(#${sky})`} />
      <circle cx="590" cy="330" r="74" fill="#F59E0B" fillOpacity="0.3" />
      <circle cx="590" cy="330" r="64" fill="#FDE68A" />
      {[[90, 150], [210, 90], [330, 200], [470, 120], [700, 170], [140, 300], [740, 80], [400, 60]].map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r="4" fill="#D4E9FD" />
      ))}
      <g fill="#FFFFFF" fillOpacity="0.7">
        <ellipse cx="180" cy="250" rx="70" ry="22" />
        <ellipse cx="225" cy="232" rx="46" ry="24" />
        <ellipse cx="640" cy="450" rx="60" ry="18" />
        <ellipse cx="680" cy="434" rx="38" ry="20" />
      </g>
      <path d="M0 640 L110 520 L190 590 L310 450 L430 580 L540 490 L660 600 L800 520 V820 H0 Z" fill="#13698F" fillOpacity="0.35" />
      <path d="M0 760 L150 560 L260 680 L420 430 L560 650 L660 560 L800 720 V880 H0 Z" fill={`url(#${near})`} />
      <path d="M420 430 L376 510 L402 500 L420 530 L440 498 L468 512 Z" fill="#FFFFFF" />
      <path d="M150 560 L118 612 L140 604 L152 626 L170 600 L186 612 Z" fill="#FFFFFF" />
      <path d="M660 560 L634 600 L652 594 L662 612 L676 592 L690 602 Z" fill="#FFFFFF" />
      <path d="M0 840 Q200 800 400 830 T800 820 V1000 H0 Z" fill="#EAF4FE" />
      <circle cx="120" cy="900" r="3" fill="#D4E9FD" />
      <circle cx="300" cy="940" r="4" fill="#D4E9FD" />
      <circle cx="560" cy="910" r="3" fill="#D4E9FD" />
      <circle cx="700" cy="950" r="4" fill="#D4E9FD" />
    </svg>
  );
}

/** Desktop: fills the right column. Phone: a header band of 140 px (`AuthSplit` places each). */
export function AuthIllustration({ pose, variant }: { pose: MascotPose; variant: "panel" | "band" }) {
  const id = useId().replace(/:/g, "");
  if (variant === "band") {
    return (
      <div className="relative h-[140px] overflow-hidden lg:hidden">
        <Scene prefix={`${id}b`} viewBox="0 450 800 300" />
        <Mascot pose={pose} size={72} eager className="absolute bottom-0 right-6" />
      </div>
    );
  }
  return (
    <div className="relative hidden overflow-hidden bg-[#DFF1FF] lg:block">
      <Scene prefix={`${id}p`} viewBox="0 0 800 1000" />
      <Mascot pose={pose} size={260} eager className="absolute bottom-[8%] left-1/2 -translate-x-1/2" />
    </div>
  );
}
