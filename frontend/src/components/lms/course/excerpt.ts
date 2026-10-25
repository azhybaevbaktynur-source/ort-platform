// Phase 6b S5c (UX T23): list excerpts arrive cut at a fixed length (server `EXCERPT = 200`), often mid-word.
// Show them on one flowing line, cut back to the last whole word and end with an ellipsis.
const SERVER_EXCERPT = 200;

export function excerptText(text: string | null | undefined, max = SERVER_EXCERPT): string {
  const flat = (text ?? "").replace(/\s+/g, " ").trim();
  const truncated = (text ?? "").length >= SERVER_EXCERPT || flat.length > max;
  if (!truncated) return flat;
  const cut = flat.slice(0, Math.min(max, flat.length));
  const space = cut.lastIndexOf(" ");
  const word = space > cut.length * 0.6 ? cut.slice(0, space) : cut;
  return `${word.replace(/[\s.,;:!?…-]+$/, "")}…`;
}
