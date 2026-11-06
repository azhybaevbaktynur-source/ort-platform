import { API_BASE_URL } from "@/lib/apiBase";

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

// --- UX rework S1 begin --- (UX_REWORK_DESIGN F: Student view is a real session of the course's test student)
// Per tab: `sessionStorage["studentView"] = {courseId, token, expiresAt}`. While it is set, every request of this tab
// uses that token, so the server treats the tab as an ordinary student. The teacher's own `ort_token` stays untouched
// in localStorage (other tabs keep working as the teacher); only entering and resetting send it.
const STUDENT_VIEW_KEY = "studentView";

export interface StudentViewSession {
  courseId: string;
  token: string;
  /** ms since the epoch */
  expiresAt: number;
}

export function getStudentView(): StudentViewSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STUDENT_VIEW_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as StudentViewSession;
    return v && v.token && v.courseId ? v : null;
  } catch {
    return null;
  }
}

function storeStudentView(v: StudentViewSession | null): void {
  try {
    if (v) window.sessionStorage.setItem(STUDENT_VIEW_KEY, JSON.stringify(v));
    else window.sessionStorage.removeItem(STUDENT_VIEW_KEY);
  } catch {
    // storage blocked: the tab simply stays the teacher's
  }
}

function coursePage(courseId: string): string {
  const m = window.location.pathname.match(/^\/(en|ky|ru)(?=\/|$)/);
  return `/${m ? m[1] : "ru"}/courses/${encodeURIComponent(courseId)}`;
}

/** POST with the real teacher token (never the tab's test student). Errors carry `status` and `code`, as `LmsApiError`. */
async function studentViewPost(path: string): Promise<StudentViewSession> {
  const token = localStorage.getItem("ort_token");
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const code = data?.error?.code || (res.status === 403 ? "forbidden" : res.status === 404 ? "not_found" : "unknown");
    throw Object.assign(new Error(code), { status: res.status, code, details: data?.error?.details || {} });
  }
  return { courseId: data.course_id, token: data.access_token, expiresAt: Date.now() + data.expires_in * 1000 };
}

/** Starts the mode in this tab and opens the course home as the test student. */
export async function enterStudentView(courseId: string): Promise<void> {
  const session = await studentViewPost(`/courses/${encodeURIComponent(courseId)}/student-view`);
  storeStudentView(session);
  window.location.assign(coursePage(courseId));
}

/** Retires the test student and continues as a new one (same tab, the course home). */
export async function resetStudentView(): Promise<void> {
  const current = getStudentView();
  if (!current) return;
  const session = await studentViewPost(`/courses/${encodeURIComponent(current.courseId)}/student-view/reset`);
  storeStudentView(session);
  window.location.assign(coursePage(current.courseId));
}

/** Ends the mode: back to the course as the teacher. */
export function leaveStudentView(): void {
  const current = getStudentView();
  storeStudentView(null);
  if (current) window.location.assign(coursePage(current.courseId));
}

/** Call on a 401: a dead test-student token ends the mode, and the teacher is never logged out by it. */
export function studentViewUnauthorized(status: number): void {
  if (status === 401 && getStudentView()) leaveStudentView();
}
// --- UX rework S1 end ---

// --- Phase 11 S3 begin --- (PHASE_11_DESIGN 3.3, invariant 1: the consent gate)
const GATE_OPEN_PATH = /^\/(privacy|policies|parent)(\/|$)|^\/courses\/[^/]+\/attempts\/[^/]+$/;

/**
 * Pages that stay on screen on `consent_required`: the ones that lift the gate, the public policies, the player, and the
 * parent's pages (there the code means the child's consent is pending, and the page itself shows the consent screen).
 */
export function gateOpenPath(rest: string): boolean {
  return GATE_OPEN_PATH.test(rest);
}

/**
 * S1 admin security: a platform admin without two-step login (ADMIN_MFA_REQUIRED) is refused everywhere with 403
 * `mfa_enrollment_required`; the app sends them to the setup page instead of showing errors.
 */
export function mfaEnrollmentRedirect(code: string | undefined): void {
  if (code !== "mfa_enrollment_required" || typeof window === "undefined") return;
  const m = window.location.pathname.match(/^\/(en|ky|ru)(?=\/|$)/);
  const target = `/${m ? m[1] : "ru"}/admin/security`;
  if (window.location.pathname !== target) window.location.assign(target);
}

/** A refused request (403 `consent_required`) sends the person to `/privacy`; an open attempt is never interrupted. */
export function consentRequiredRedirect(code: string | undefined): void {
  if (code !== "consent_required" || typeof window === "undefined") return;
  const m = window.location.pathname.match(/^\/(en|ky|ru)(?=\/|$)/);
  if (gateOpenPath(window.location.pathname.slice(m ? m[0].length : 0))) return;
  window.location.assign(`/${m ? m[1] : "ru"}/privacy`);
}
// --- Phase 11 S3 end ---

export async function getAuthHeader(): Promise<Record<string, string>> {
  // Backend JWT saved at login. Without it no header is sent and the API answers 401.
  if (typeof window !== "undefined") {
    const token = getStudentView()?.token ?? localStorage.getItem("ort_token");
    if (token) {
      return { Authorization: `Bearer ${token}` };
    }
  }
  return {};
}

export async function apiClient<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers = {}, ...customConfig } = options;

  // Clean endpoint path
  let cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  // Strip /api/v1 if caller passed it by accident
  if (cleanEndpoint.startsWith("/api/v1/")) {
    cleanEndpoint = cleanEndpoint.replace("/api/v1", "");
  }

  let url = `${API_BASE_URL}${cleanEndpoint}`;

  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null) {
        searchParams.append(key, String(val));
      }
    });
    const qs = searchParams.toString();
    if (qs) {
      url += `?${qs}`;
    }
  }

  const isFormData = typeof FormData !== "undefined" && customConfig.body instanceof FormData;
  const authHeader = await getAuthHeader();

  const reqHeaders: Record<string, string> = {
    ...(!isFormData && { "Content-Type": "application/json" }),
    ...authHeader,
    ...(headers as Record<string, string>),
  };

  let response: Response;
  try {
    response = await fetch(url, {
      cache: "no-store",
      ...customConfig,
      headers: reqHeaders,
    });
  } catch (networkErr: any) {
    // Phase 6b: one message per UI language (no i18n context here); the page sets <html lang>.
    const NETWORK_ERROR: Record<string, string> = {
      en: "No connection to the server. Check your internet and try again.",
      ky: "Сервер менен байланыш жок. Интернетти текшерип, кайра аракет кылыңыз.",
      ru: "Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.",
    };
    const uiLang = typeof document !== "undefined" ? document.documentElement.lang : "";
    throw new Error(NETWORK_ERROR[uiLang] || NETWORK_ERROR.ru);
  }

  if (!response.ok) {
    studentViewUnauthorized(response.status);
    let errorDetail = `API Request Failed (${response.status})`;
    try {
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const errorJson = await response.json();
        consentRequiredRedirect(errorJson?.error?.code); // Phase 11 S3
        mfaEnrollmentRedirect(errorJson?.error?.code); // S1
        errorDetail = errorJson.detail || errorDetail;
      } else {
        const text = await response.text();
        if (text && !text.includes("<!DOCTYPE")) {
          errorDetail = text.slice(0, 200);
        }
      }
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  return (await response.text()) as unknown as T;
}
