import type { MetadataRoute } from "next";
import ruDict from "@/lib/i18n/ru.json";

/*
 * S5 installable app (docs/ROADMAP_EXAM_PREP.md): the web app manifest, served at /manifest.webmanifest and linked
 * from every page by Next.js. The name is the platform name placeholder `common.appName` (ru.json): changing it there
 * renames the installed app at the next build. The app opens on /ru/; the interface then follows the language the
 * person picked before (LanguageProvider, localStorage `ort_preferred_language`). Colours: brand-600 and slate-50
 * (tailwind.config.ts, the body background). Icons: public/icons, drawn by scripts/pwa_icons.mjs.
 */
export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  const name = ruDict.common.appName;
  return {
    id: "/",
    name,
    short_name: name,
    description: ruDict.landing.badge,
    lang: "ru",
    start_url: "/ru/",
    scope: "/",
    display: "standalone",
    orientation: "any",
    theme_color: "#2563eb",
    background_color: "#f8fafc",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
