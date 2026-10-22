"use client";

import { useRef } from "react";

/** Native HTML5 drag reorder for a flat list; up/down buttons remain the accessible path. */
export function useDragReorder(onMove: (from: number, to: number) => void, enabled: boolean) {
  const from = useRef<number | null>(null);
  return (index: number) =>
    enabled
      ? {
          draggable: true as const,
          onDragStart: (e: React.DragEvent) => { e.stopPropagation(); from.current = index; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", String(index)); },
          onDragOver: (e: React.DragEvent) => { if (from.current !== null) e.preventDefault(); },
          onDrop: (e: React.DragEvent) => {
            e.preventDefault();
            if (from.current !== null) e.stopPropagation();
            const f = from.current;
            from.current = null;
            if (f !== null && f !== index) onMove(f, index);
          },
          onDragEnd: () => { from.current = null; },
        }
      : {};
}
