import React from "react";
import type { Metadata, Viewport } from "next";
import ruDict from "@/lib/i18n/ru.json";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "ОРТ / ЖРТ Даярдоо Платформасы",
  description: "Кыргызстандын окуучулары үчүн бекер ЖРТ даярдоо жана сыноо платформасы",
  // S5 installable app: icons (public/icons, scripts/pwa_icons.mjs) and the iOS home screen tags; the manifest is app/manifest.ts
  icons: {
    icon: [
      { url: "/icons/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
  appleWebApp: { capable: true, title: ruDict.common.appName, statusBarStyle: "default" },
  formatDetection: { telephone: false },
};

// Item 4 (phone sheets): the page extends under the browser bars; sheets and the tab bar pad with env(safe-area-inset-*)
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

// S5: Chrome fires `beforeinstallprompt` once, often before React hydrates; keep it for the "Install the app" menu entry
// (components/pwa/PwaProvider.tsx). Inline scripts are allowed by the CSP (next.config.ts).
const CAPTURE_INSTALL_PROMPT =
  "window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();window.__pwaInstallPrompt=e;window.dispatchEvent(new Event('pwa-install-available'));});";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html>
      <head>
        <script dangerouslySetInnerHTML={{ __html: CAPTURE_INSTALL_PROMPT }} />
      </head>
      <body suppressHydrationWarning className="min-h-screen bg-slate-50 antialiased font-sans">
        {children}
      </body>
    </html>
  );
}
