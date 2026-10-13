// When running in the browser, relative "/api/v1" is proxied by Next.js rewrites to FastAPI (http://127.0.0.1:8000/api/v1).
// Alternatively, if NEXT_PUBLIC_API_URL is explicitly set, use that.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

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
      ...customConfig,
      headers: reqHeaders,
    });
  } catch (networkErr: any) {
    throw new Error(networkErr.message || "Серверге туташуу оңундан чыккан жок / Ошибка сети");
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
