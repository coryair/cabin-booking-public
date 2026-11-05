type CacheEntry<T> = {
  value: T;
  expiresAt: number;
};

type FetchJsonOptions = {
  ttlMs?: number;
  dedupe?: boolean;
  bypassCache?: boolean;
};

const responseCache = new Map<string, CacheEntry<unknown>>();
const requestGenerations = new Map<string, number>();
const inFlight = new Map<string, { generation: number; promise: Promise<unknown> }>();

function requestKey(url: string, init?: RequestInit): string {
  const method = (init?.method || "GET").toUpperCase();
  const credentials = init?.credentials || "same-origin";
  return `${method}:${credentials}:${url}`;
}

function requestUrl(key: string): string {
  const thirdColon = key.indexOf(":", key.indexOf(":") + 1);
  return thirdColon >= 0 ? key.slice(thirdColon + 1) : "";
}

export function invalidateGetCache(urlPrefix: string): void {
  for (const key of responseCache.keys()) {
    if (key.startsWith("GET:") && requestUrl(key).startsWith(urlPrefix)) {
      responseCache.delete(key);
    }
  }

  for (const [key, generation] of requestGenerations) {
    if (key.startsWith("GET:") && requestUrl(key).startsWith(urlPrefix)) {
      requestGenerations.set(key, generation + 1);
    }
  }
}

export async function fetchJsonCached<T>(
  url: string,
  init?: RequestInit,
  options?: FetchJsonOptions,
): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  if (method !== "GET") {
    return apiRequest<T>(url, init);
  }

  const ttlMs = options?.ttlMs ?? 0;
  const bypassCache = options?.bypassCache ?? false;
  const dedupe = options?.dedupe ?? !bypassCache;
  const key = requestKey(url, init);
  const now = Date.now();
  const currentGeneration = requestGenerations.get(key) ?? 0;

  if (!bypassCache && ttlMs > 0) {
    const cached = responseCache.get(key);
    if (cached && cached.expiresAt > now) {
      return cached.value as T;
    }
  }

  if (dedupe) {
    const existing = inFlight.get(key);
    if (existing?.generation === currentGeneration) return existing.promise as Promise<T>;
  }


  const requestGeneration = currentGeneration + 1;
  requestGenerations.set(key, requestGeneration);

  const promise = (async () => {
    const requestInit = bypassCache
      ? { ...init, cache: init?.cache ?? "no-store" as RequestCache }
      : init;
    const data = await apiRequest<T>(url, requestInit);
    if (ttlMs > 0 && requestGenerations.get(key) === requestGeneration) {
      responseCache.set(key, {
        value: data,
        expiresAt: Date.now() + ttlMs,
      });
    }
    return data;
  })();

  if (dedupe) {
    inFlight.set(key, { generation: requestGeneration, promise });
  }

  try {
    return await promise;
  } finally {
    if (dedupe) {
      if (inFlight.get(key)?.promise === promise) {
        inFlight.delete(key);
      }
    }
  }
}
import { apiRequest } from "../api/client";
