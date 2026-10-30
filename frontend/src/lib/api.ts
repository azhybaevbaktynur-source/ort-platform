import { API_BASE_URL } from "@/lib/apiBase";

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

export async function getAuthHeader(): Promise<Record<string, string>> {
  // Backend JWT saved at login. Without it no header is sent and the API answers 401.
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("ort_token");
    if (token) {
      return { Authorization: `Bearer ${token}` };
    }
  }
  return {};
}

// --- Phase 8c S1 begin --- (PHASE_8C_DESIGN §6.2: read-only Student view)
// The "Student view" button sets `sessionStorage["studentView:{courseId}"] = "1"`; while it is set, every request to
// that course's routes (`/courses/{courseId}` and below) carries `X-View-As: student`. Never other courses, `/me/*`
// or platform routes. The server downgrades only a real teacher/assistant role, for reads; it refuses writes
// (403 `student_view_read_only`) except the staff preview attempt. The mode ends with the tab (sessionStorage).
const STUDENT_VIEW_PREFIX = "studentView:";
const COURSE_PATH = /(?:^|\/api\/v1)\/courses\/([0-9a-fA-F-]{36})(?=[/?#]|$)/;

export function isStudentView(courseId: string | null | undefined): boolean {
  if (!courseId || typeof window === "undefined") return false;
  try {
    return window.sessionStorage.getItem(STUDENT_VIEW_PREFIX + courseId) === "1";
  } catch {
    return false;
  }
}

export function setStudentView(courseId: string, on: boolean): void {
  if (typeof window === "undefined") return;
  try {
    if (on) window.sessionStorage.setItem(STUDENT_VIEW_PREFIX + courseId, "1");
    else window.sessionStorage.removeItem(STUDENT_VIEW_PREFIX + courseId);
  } catch {
    // storage blocked: the mode simply does not start
  }
}

/** `{ "X-View-As": "student" }` for a request path of a course in Student view, else `{}`. `path` is relative to the
 * API base (`/courses/...`) or a full URL path (`/api/v1/courses/...`). */
export function viewAsHeader(path: string): Record<string, string> {
  const m = path.split("?", 1)[0].match(COURSE_PATH);
  return m && isStudentView(m[1]) ? { "X-View-As": "student" } : {};
}
// --- Phase 8c S1 end ---

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
    ...viewAsHeader(cleanEndpoint), // Phase 8c S1
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
    let errorDetail = `API Request Failed (${response.status})`;
    try {
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const errorJson = await response.json();
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
