import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Intercept Admin routes
  const isAdminRoute =
    pathname.includes("/exams") ||
    pathname.includes("/questions") ||
    pathname.includes("/bulk-upload") ||
    pathname.includes("/students") ||
    (pathname.includes("/analytics") && !pathname.includes("/student"));

  if (isAdminRoute) {
    const roleCookie = request.cookies.get("ort_role")?.value;
    const tokenCookie = request.cookies.get("ort_token")?.value;

    // Detect language prefix
    const langMatch = pathname.match(/^\/(en|ky|ru)/);
    const lang = langMatch ? langMatch[1] : "ky";

    // If not authenticated or not admin, strictly kick to student dashboard
    if (!tokenCookie || roleCookie !== "admin") {
      const redirectUrl = new URL(`/${lang}/dashboard`, request.url);
      return NextResponse.redirect(redirectUrl);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/(en|ky|ru)/exams/:path*",
    "/(en|ky|ru)/exams",
    "/(en|ky|ru)/questions/:path*",
    "/(en|ky|ru)/questions",
    "/(en|ky|ru)/bulk-upload/:path*",
    "/(en|ky|ru)/bulk-upload",
    "/(en|ky|ru)/analytics/:path*",
    "/(en|ky|ru)/analytics",
    "/(en|ky|ru)/students/:path*",
    "/(en|ky|ru)/students",
  ],
};

