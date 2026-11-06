import type { Config } from "tailwindcss";
import colors from "tailwindcss/colors";

/*
 * Design tokens (Phase 6b S5a, docs/UX_GUIDELINES.md §5, PHASE_6_DESIGN.md §8.3).
 * - brand-*: primary actions and links. The values are Tailwind blue, the same as the
 *   brand blue used since Phase 1 (50/100/500/600/700/800/900 unchanged).
 * - slate: text and borders (Tailwind slate + the two extra dark shades used before).
 * - success / warning / danger: full scales for states. Text on white uses the 700 shade
 *   (contrast >= 4.5:1); filled buttons use the 600 shade with white text.
 * - gold: achievements only (for example the ORT golden certificate).
 * Spacing is the Tailwind default 4 px scale. One font family (`font-sans`).
 *
 * Student UI U1 (docs/phases/STUDENT_UI_DESIGN.md §1): navy, tag, acc, heat and chart colours, the `control` and
 * `card` radii, and Inter for the student shell only (see `fontFamily`). The same values are CSS variables on
 * `:root` in styles/globals.css.
 */

/** The system font stack every frame used before Student UI U1 (the teacher and admin frames still do). */
const SYSTEM_STACK = [
  "system-ui",
  "-apple-system",
  "BlinkMacSystemFont",
  '"Segoe UI"',
  "Roboto",
  "Oxygen",
  "Ubuntu",
  "Cantarell",
  '"Open Sans"',
  '"Helvetica Neue"',
  "sans-serif",
];

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Student UI colour (STUDENT_UI_DESIGN §1.1): `brand` reads CSS variables (space-separated RGB channels, so
        // opacity modifiers keep working). `:root` in styles/globals.css holds exactly the blue used since Phase 1
        // (Tailwind blue); the student frame (`.student-theme`) overrides the variables with the owner's sky blue.
        brand: Object.fromEntries(
          [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((k) => [k, `rgb(var(--brand-${k}) / <alpha-value>)`]),
        ),
        slate: {
          850: "#152033",
          950: "#0b1120",
        },
        success: { ...colors.emerald },
        warning: { ...colors.amber },
        danger: { ...colors.red },
        gold: {
          50: colors.amber[50],
          100: colors.amber[100],
          200: colors.amber[200],
          300: colors.amber[300],
          400: "#fbbf24",
          500: "#f59e0b",
          600: "#d97706",
          700: colors.amber[700],
          800: colors.amber[800],
          900: colors.amber[900],
        },
        // --- Student UI U1 ---
        // the student sidebar, the phone top bar's brand mark and the "More" sheet header
        // (Student UI colour: CSS variables like `brand`; `.student-theme` turns them into the owner's teal)
        navy: { 800: "rgb(var(--navy-800) / <alpha-value>)", 900: "rgb(var(--navy-900) / <alpha-value>)" },
        // ORT section pills: `bg-tag-<key>` with `text-tag-<key>-fg`
        tag: {
          math1: { DEFAULT: "#e0f2fe", fg: "#075985" },
          math2: { DEFAULT: "#e0e7ff", fg: "#3730a3" },
          analogies: { DEFAULT: "#ede9fe", fg: "#5b21b6" },
          reading: { DEFAULT: "#ccfbf1", fg: "#115e59" },
          grammar: { DEFAULT: "#ffedd5", fg: "#9a3412" },
        },
        // accuracy bands (< 60 %, 60-84 %, >= 85 %): fill `bg-acc-<band>`, text `text-acc-<band>-text`
        acc: {
          low: { DEFAULT: "#f43f5e", text: "#be123c" },
          mid: { DEFAULT: "#f59e0b", text: "#b45309" },
          high: { DEFAULT: "#10b981", text: "#047857" },
        },
        // activity heatmap levels (0, 1-4, 5-14, 15-29, 30+ answers a day)
        heat: { 0: "#eef2f7", 1: "#c7d7fb", 2: "#8fb0f6", 3: "#4f82ee", 4: "#1d4ed8" },
        // chart series (correct = chart-2, wrong = acc-low)
        chart: { 1: "#2563eb", 2: "#10b981", 3: "#f97316", 4: "#8b5cf6", 5: "#f59e0b" },
      },
      // Student UI U1: the student shell defines `--font-inter` (next/font, lib/fonts.ts) and sets `font-sans` again;
      // everywhere else the variable is unset and `font-sans` resolves to exactly the system stack used before.
      // `font-system` is the system stack alone.
      fontFamily: {
        sans: ["var(--font-inter, system-ui)", ...SYSTEM_STACK.slice(1)],
        system: SYSTEM_STACK,
      },
      // Student UI U1: controls (buttons, inputs, sidebar pills) and cards
      borderRadius: {
        control: "12px",
        card: "16px",
      },
    },
  },
  plugins: [],
};
export default config;
