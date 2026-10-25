// Phase 6b S5c: button class strings of the staff course screens, taken from the design system
// (`buttonClasses`): same names as `content/ui.ts` so call sites stay as they are, 44 px targets on phones.
// `content/ui.ts` itself is unchanged because student and ORT lobby screens still use it.
import { buttonClasses } from "@/components/ui";

export const btnPrimary = buttonClasses({ variant: "primary", size: "sm" });
export const btnSecondary = buttonClasses({ variant: "secondary", size: "sm" });
export const btnDanger = buttonClasses({
  variant: "secondary",
  size: "sm",
  className: "border-danger-200 text-danger-700 hover:bg-danger-50 active:bg-danger-50",
});
export const btnSmall = buttonClasses({ variant: "secondary", size: "sm", className: "px-2.5" });
