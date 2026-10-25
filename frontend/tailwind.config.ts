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
 */
const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eff6ff",
          100: "#dbeafe",
          200: colors.blue[200],
          300: colors.blue[300],
          400: colors.blue[400],
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e40af",
          900: "#1e3a8a",
          950: colors.blue[950],
        },
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
      },
      fontFamily: {
        sans: [
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
        ],
      },
    },
  },
  plugins: [],
};
export default config;
