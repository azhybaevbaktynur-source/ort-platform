import { Inter } from "next/font/google";

/*
 * Student UI U1 (docs/phases/STUDENT_UI_DESIGN.md §1): Inter for the student shell only. Self-hosted by Next at build
 * time (served from /_next/static, CSP `font-src 'self'`). `cyrillic-ext` carries the Kyrgyz letters ң ө ү.
 *
 * `inter.variable` defines `--font-inter`; the shell puts it next to `font-sans` (tailwind.config.ts), so only the
 * shell's subtree switches font. Never put it on <html>, <body> or the AppHeader frame: the teacher, admin, lobby and
 * attempt frames keep the system font (ORT baseline screenshots). `preload: false`: the files are fetched only where
 * the font is used, so the exam routes never download them.
 */
export const inter = Inter({
  subsets: ["latin", "cyrillic", "cyrillic-ext"],
  display: "swap",
  variable: "--font-inter",
  preload: false,
});
