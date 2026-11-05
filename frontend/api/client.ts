export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly payload: unknown;

  constructor(status: number, detail: string, payload: unknown = null) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.payload = payload;
  }
}
function getErrorDetail(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const candidate = payload as { detail?: unknown; error?: unknown; message?: unknown };
    for (const value of [candidate.detail, candidate.error, candidate.message]) {
      if (typeof value === "string" && value.trim()) return value;
    }
  }
  if (typeof payload === "string" && payload.trim()) return payload;
  return fallback;
}

async function parseResponse(res: Response): Promise<unknown> {
  if (res.status === 204 || res.status === 205) return undefined;

  const text = await res.text();
  if (!text) return undefined;

  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("json")) {
    try {
      return JSON.parse(text) as unknown;
    } catch {
      throw new ApiError(res.status, "The server returned invalid JSON.", text);
    }
  }

  return text;
}

export async function apiRequest<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const isFormBody = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (init.body != null && !isFormBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(url, {
    ...init,
    credentials: init.credentials ?? "include",
    headers,
  });
  const payload = await parseResponse(res);

  if (!res.ok) {
    throw new ApiError(
      res.status,
      getErrorDetail(payload, res.statusText || `Request failed (${res.status})`),
      payload,
    );
  }

  return payload as T;
}

export function jsonRequest(method: "POST" | "PUT" | "PATCH", body?: unknown): RequestInit {
  return {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}
