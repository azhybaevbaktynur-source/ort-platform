import { notFound } from "next/navigation";
import { UiShowcase } from "./UiShowcase";

// Dev-only showcase of the design system (Phase 6b S5a), used for the UX gate screenshots.
export default function DevUiPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <UiShowcase />;
}
