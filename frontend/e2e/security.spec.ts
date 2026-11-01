// Phase 11 S4 (PHASE_11_DESIGN 5.2, 5.5): the page CSP, the CSP watcher of helpers.ts, rolling tokens, auth calls.
import { expect, test, type Page } from "@playwright/test";
import { tr, watchCsp } from "./helpers";

const API = process.env.NEXT_PUBLIC_API_URL || `http://127.0.0.1:${process.env.E2E_API_PORT || 8765}`;

/** Unsigned on purpose: the browser never verifies a token, and these tests answer every call that would. */
function token(claims: Record<string, unknown>): string {
  const part = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${part({ alg: "HS256", typ: "JWT" })}.${part(claims)}.x`;
}

const NOW = () => Math.floor(Date.now() / 1000);
const DAY = 86400;

/** Signed in with `tok`; returns the list of refresh calls. */
async function session(page: Page, tok: string, extra?: { studentView?: boolean }): Promise<string[]> {
  const calls: string[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/auth/refresh")) {
      calls.push(route.request().headers()["authorization"]);
      await route.fulfill({ json: { access_token: "fresh-token", token_type: "bearer", user: {} } });
    } else if (url.includes("/auth/me")) {
      await route.fulfill({ json: { id: "u1", email: "u@test.example", is_platform_admin: false, teacher_status: "none" } });
    } else {
      await route.fulfill({ status: 404, json: { error: { code: "not_found", message: "x" } } });
    }
  });
  await page.addInitScript(([t, view]) => {
    if (window.localStorage.getItem("ort_token") === null) window.localStorage.setItem("ort_token", t);
    window.localStorage.setItem("ort_dev_auth_user", JSON.stringify({ uid: "u1", email: "u@test.example", displayName: "U", is_platform_admin: false, teacher_status: "none" }));
    if (view) window.sessionStorage.setItem("studentView", JSON.stringify({ courseId: "c1", token: "test-student-token", expiresAt: Date.now() + 1e7 }));
  }, [tok, Boolean(extra?.studentView)] as const);
  return calls;
}

const settleRefresh = (page: Page) => page.waitForTimeout(2500); // START_DELAY_MS + the answer

test.describe("rolling tokens", () => {
  test("a token older than 12 h is swapped once", async ({ page }) => {
    const old = token({ sub: "u1", iat: NOW() - DAY, exp: NOW() + 2 * DAY });
    const calls = await session(page, old);
    await page.goto("/ru/courses");
    await settleRefresh(page);
    expect(calls).toEqual([`Bearer ${old}`]);
    expect(await page.evaluate(() => localStorage.getItem("ort_token"))).toBe("fresh-token");
  });

  test("a token issued before this release (no iat) is swapped", async ({ page }) => {
    const calls = await session(page, token({ sub: "u1", exp: NOW() + 6 * DAY }));
    await page.goto("/ru/courses");
    await settleRefresh(page);
    expect(calls.length).toBe(1);
  });

  test("a young token is left alone", async ({ page }) => {
    const young = token({ sub: "u1", iat: NOW() - 3600, exp: NOW() + 2 * DAY });
    const calls = await session(page, young);
    await page.goto("/ru/courses");
    await settleRefresh(page);
    expect(calls).toEqual([]);
    expect(await page.evaluate(() => localStorage.getItem("ort_token"))).toBe(young);
  });

  for (const path of ["/ru/courses/c1/attempts/a1", "/ru/courses/c1/assessments/x1/attempts/a1"]) {
    test(`never inside the player: ${path}`, async ({ page }) => {
      const calls = await session(page, token({ sub: "u1", iat: NOW() - DAY, exp: NOW() + 2 * DAY }));
      await page.goto(path);
      await settleRefresh(page);
      expect(calls).toEqual([]);
    });
  }

  test("a Student view tab never touches the real session", async ({ page }) => {
    const old = token({ sub: "u1", iat: NOW() - DAY, exp: NOW() + 2 * DAY });
    const calls = await session(page, old, { studentView: true });
    await page.goto("/ru/courses");
    await settleRefresh(page);
    expect(calls).toEqual([]);
    expect(await page.evaluate(() => localStorage.getItem("ort_token"))).toBe(old);
  });

  test("a failed refresh keeps the session", async ({ page }) => {
    const old = token({ sub: "u1", iat: NOW() - DAY, exp: NOW() + 2 * DAY });
    await session(page, old);
    await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ status: 503, json: {} }));
    await page.goto("/ru/courses");
    await settleRefresh(page);
    expect(await page.evaluate(() => localStorage.getItem("ort_token"))).toBe(old);
  });
});

test.describe("page CSP", () => {
  test("headers are on pages and allow what the app loads", async ({ page, request }) => {
    const res = await request.get("/ru/login");
    const csp = res.headers()["content-security-policy"];
    expect(csp).toContain("script-src 'self' 'unsafe-inline'");
    expect(csp).not.toContain("unsafe-eval");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toMatch(/img-src [^;]*https:\/\/\*\.r2\.dev/);
    expect(csp).toContain(`connect-src 'self' ${new URL(API).origin}`);
    expect(res.headers()["x-content-type-options"]).toBe("nosniff");
    expect(res.headers()["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    expect(res.headers()["permissions-policy"]).toContain("camera=()");

    // An R2 image, a data image and KaTeX's fonts raise no violation; a foreign image does.
    const violations: string[] = [];
    page.on("console", (m) => { if (/Content Security Policy/i.test(m.text())) violations.push(m.text()); });
    await page.goto("/ru/login");
    await page.evaluate(async () => {
      const add = (src: string) => new Promise((done) => {
        const img = document.createElement("img");
        img.onload = img.onerror = done;
        img.src = src;
        document.body.appendChild(img);
      });
      await add("https://pub-0123456789.r2.dev/img/none.webp");
      await add("data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==");
    });
    expect(violations).toEqual([]);
    await page.evaluate(() => new Promise((done) => {
      const img = document.createElement("img");
      img.onload = img.onerror = done;
      img.src = "https://foreign.example/x.png";
      document.body.appendChild(img);
    }));
    await expect.poll(() => violations.length).toBeGreaterThan(0);
  });

  test("the /api rewrite keeps the API's own headers", async ({ request }) => {
    const res = await request.get("/api/v1/auth/ping");
    expect(res.status()).toBe(200);
    expect(res.headers()["content-security-policy"]).toBeUndefined();
  });

  test("the watcher fails a test on a violation", async ({ page }) => {
    test.fail(); // proves the guard of every other spec: this test must end red
    watchCsp(page);
    await page.goto("/ru/login");
    await page.evaluate(() => { const img = document.createElement("img"); img.src = "https://foreign.example/x.png"; document.body.appendChild(img); });
    await page.waitForTimeout(500);
  });
});

test.describe("auth calls", () => {
  test("login goes straight to the API and a 429 reads as a sentence", async ({ page }) => {
    const seen: string[] = [];
    await page.route("**/api/v1/auth/login", async (route) => {
      seen.push(route.request().url());
      await route.fulfill({ status: 429, headers: { "access-control-allow-origin": "*" },
        json: { detail: { code: "rate_limited", message: "Too many", retryAfterSeconds: 30 } } });
    });
    await page.goto("/ru/login");
    await page.locator('input[type="email"]').fill("a@test.example");
    await page.locator('input[type="password"]').fill("password-1");
    await page.locator('button[type="submit"]').click();
    await expect(page.getByText(tr("ru", "auth.errors.rate_limited"))).toBeVisible();
    expect(seen).toEqual([`${new URL(API).origin}/api/v1/auth/login`]);
  });

  test("forgot password: straight to the API and a 429 reads as a sentence", async ({ page }) => {
    const seen: string[] = [];
    await page.route("**/api/v1/auth/forgot-password", async (route) => {
      seen.push(route.request().url());
      await route.fulfill({ status: 429, headers: { "access-control-allow-origin": "*" },
        json: { detail: { code: "rate_limited", message: "Too many", retryAfterSeconds: 30 } } });
    });
    await page.goto("/ru/forgot-password");
    await page.locator('input[type="email"]').fill("a@test.example");
    await page.locator('button[type="submit"]').click();
    await expect(page.getByText(tr("ru", "auth.errors.rate_limited"))).toBeVisible();
    expect(seen).toEqual([`${new URL(API).origin}/api/v1/auth/forgot-password`]);
  });
});
