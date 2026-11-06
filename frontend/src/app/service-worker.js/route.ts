/*
 * S5 installable app: the registered service worker script. One line that names the build and imports the
 * hand-written worker (public/sw.js). Its bytes change with every build, so the browser's own update check finds a
 * new version even in an app that stays open for days; the new worker then waits for the person (UpdateToast).
 * Rendered once at build time (a static file on the CDN).
 */
export const dynamic = "force-static";

export function GET() {
  const version = process.env.NEXT_PUBLIC_SW_VERSION || "dev";
  return new Response(`self.SW_VERSION=${JSON.stringify(version)};importScripts("/sw.js");\n`, {
    headers: {
      "Content-Type": "text/javascript; charset=utf-8",
      "Cache-Control": "no-cache",
    },
  });
}
