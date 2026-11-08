// FB8 S0 (STAFF_UX_AUDIT §1): the menu moved to `components/ui/OverflowMenu.tsx`; this file keeps the old import path
// and names working for existing callers. New code imports `OverflowMenu` from "@/components/ui".
export { OverflowMenu as OutlineMenu } from "@/components/ui/OverflowMenu";
export type {
  OverflowMenuItem as OutlineMenuItem,
  OverflowMenuProps as OutlineMenuProps,
  MenuGroup,
} from "@/components/ui/OverflowMenu";
