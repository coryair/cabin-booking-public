import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import { adminApi } from "./admin";
import { loadAdminDashboardData } from "./adminData";
import { calendarApi } from "./calendar";
import { ApiError, apiRequest } from "./client";
import { reservationsApi } from "./reservations";
import { authApi } from "./auth";
import { fetchJsonCached, invalidateGetCache } from "../lib/fetchCache";

type FetchCall = { url: string; init?: RequestInit };

const originalFetch = globalThis.fetch;
let calls: FetchCall[] = [];
let responses: Array<Response | Promise<Response>> = [];

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  calls = [];
  responses = [];
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    const response = responses.shift();
    if (!response) throw new Error("Test did not provide a response");
    return await response;
  }) as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("apiRequest", () => {
  it("applies same-origin credentials and parses successful JSON", async () => {
    responses.push(jsonResponse({ ok: true }));

    await expect(apiRequest<{ ok: boolean }>("/api/example")).resolves.toEqual({ ok: true });
    expect(calls).toHaveLength(1);
    expect(calls[0]?.init?.credentials).toBe("include");
  });

  it("throws a typed error using the backend detail", async () => {
    responses.push(jsonResponse({ detail: "Not allowed" }, 403));

    try {
      await apiRequest("/api/example");
      throw new Error("Expected request to fail");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).status).toBe(403);
      expect((error as ApiError).detail).toBe("Not allowed");
    }
  });

  it("reports invalid JSON instead of leaking a parser error", async () => {
    responses.push(new Response("not-json", {
      status: 502,
      headers: { "Content-Type": "application/json" },
    }));

    await expect(apiRequest("/api/example")).rejects.toThrow("The server returned invalid JSON.");
  });

  it("supports empty success responses", async () => {
    responses.push(new Response(null, { status: 204 }));
    await expect(apiRequest<void>("/api/example", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("bypasses browser caching for forced cached-request refreshes", async () => {
    responses.push(jsonResponse([{ cabin_id: "pine" }]));

    await fetchJsonCached("/api/forced-refresh-test", undefined, {
      ttlMs: 60000,
      bypassCache: true,
    });

    expect(calls[0]?.init?.cache).toBe("no-store");
  });

  it("does not let an older request overwrite refreshed cache data", async () => {
    let resolveOld!: (response: Response) => void;
    let resolveFresh!: (response: Response) => void;
    responses.push(
      new Promise<Response>((resolve) => { resolveOld = resolve; }),
      new Promise<Response>((resolve) => { resolveFresh = resolve; }),
    );

    const oldRequest = fetchJsonCached<{ value: string }>(
      "/api/cache-race-test",
      undefined,
      { ttlMs: 60000 },
    );
    invalidateGetCache("/api/cache-race-test");
    const freshRequest = fetchJsonCached<{ value: string }>(
      "/api/cache-race-test",
      undefined,
      { ttlMs: 60000, bypassCache: true, dedupe: false },
    );

    resolveFresh(jsonResponse({ value: "fresh" }));
    await expect(freshRequest).resolves.toEqual({ value: "fresh" });
    resolveOld(jsonResponse({ value: "old" }));
    await expect(oldRequest).resolves.toEqual({ value: "old" });

    await expect(fetchJsonCached<{ value: string }>(
      "/api/cache-race-test",
      undefined,
      { ttlMs: 60000 },
    )).resolves.toEqual({ value: "fresh" });
    expect(calls).toHaveLength(2);
  });
});

describe("booking and reservation API contracts", () => {
  it("updates only the cancellation-availability preference", async () => {
    responses.push(jsonResponse({
      id: 1,
      cancellation_availability_emails_enabled: false,
    }));

    await authApi.updateNotificationPreferences(false);

    expect(calls[0]?.url).toBe("/api/notification-preferences");
    expect(calls[0]?.init?.method).toBe("PUT");
    expect(JSON.parse(String(calls[0]?.init?.body))).toEqual({
      cancellation_availability_emails_enabled: false,
    });
  });

  it("validates unsubscribe with GET and confirms it with POST", async () => {
    responses.push(
      jsonResponse({ valid: true, subscribed: true, email: "s***@example.com" }),
      jsonResponse({ unsubscribed: true, email: "s***@example.com", message: "Updated" }),
    );

    await authApi.validateCancellationAvailabilityUnsubscribe("signed token");
    await authApi.unsubscribeCancellationAvailability("signed token");

    expect(calls[0]?.url).toBe(
      "/api/notification-preferences/cancellation-availability/unsubscribe?token=signed%20token",
    );
    expect(calls[0]?.init?.method).toBeUndefined();
    expect(calls[1]?.init?.method).toBe("POST");
    expect(JSON.parse(String(calls[1]?.init?.body))).toEqual({ token: "signed token" });
  });

  it("builds an encoded availability request", async () => {
    responses.push(jsonResponse({ available: true, cabins: { pine: true }, conflicts: [] }));

    const result = await calendarApi.availability("2026-08-03", "2026-08-05");
    expect(result.cabins.pine).toBe(true);
    expect(calls[0]?.url).toBe("/api/availability?start_date=2026-08-03&end_date=2026-08-05");
  });

  it("submits checkout through the shared JSON client", async () => {
    responses.push(jsonResponse({ checkout_url: "https://checkout.stripe.test/session", reservation_id: 108 }));

    const result = await reservationsApi.checkout({
      share: "fir",
      cabins: ["pine"],
      start_date: "2026-08-03",
      end_date: "2026-08-05",
      guest_count: 0,
      guest_nights: [],
      is_day_use: false,
    });

    expect(result.reservation_id).toBe(108);
    expect(calls[0]?.init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0]?.init?.body))).toMatchObject({
      share: "fir",
      cabins: ["pine"],
      is_day_use: false,
    });
  });

  it("sends an explicit policy override for an admin refund", async () => {
    responses.push(jsonResponse({
      status: "refunded",
      refund_issued: true,
      refund_amount: 200,
      message: "Refunded",
    }));

    await reservationsApi.adminRefund(42, true);

    expect(calls[0]?.url).toBe("/api/reservations/42/refund");
    expect(calls[0]?.init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0]?.init?.body))).toEqual({ override_policy: true });
  });

  it("refreshes the complete admin dataset and rejects HTTP failures", async () => {
    responses.push(
      jsonResponse([]),
      jsonResponse(null),
      jsonResponse([]),
      jsonResponse({ detail: "Admin access required" }, 403),
    );

    await expect(loadAdminDashboardData()).rejects.toThrow("Admin access required");
  });

  it("rejects successful but malformed admin collections", async () => {
    responses.push(
      jsonResponse({ detail: "wrong shape" }),
      jsonResponse(null),
      jsonResponse([]),
      jsonResponse([]),
    );

    await expect(loadAdminDashboardData()).rejects.toThrow("invalid reservation data");
  });

  it("loads typed admin collections together", async () => {
    responses.push(jsonResponse([]), jsonResponse(null), jsonResponse([]), jsonResponse([]));

    await expect(loadAdminDashboardData()).resolves.toEqual({
      reservations: [],
      season: null,
      seasons: [],
      shareholders: [],
    });
    expect(calls.map((call) => call.url)).toEqual([
      "/api/reservations?include_cancelled=true",
      "/api/booking-seasons/current",
      "/api/booking-seasons",
      "/api/shareholders",
    ]);
  });

  it("treats a missing current season as an empty optional value", async () => {
    responses.push(jsonResponse({ detail: "No booking season configured for this year" }, 404));

    await expect(adminApi.currentSeason()).resolves.toBeNull();
  });

  it("still rejects non-404 current season failures", async () => {
    responses.push(jsonResponse({ detail: "Admin access required" }, 403));

    await expect(adminApi.currentSeason()).rejects.toThrow("Admin access required");
  });

  it("uses the shared admin API for mutations", async () => {
    responses.push(jsonResponse({ id: 1, cabin_id: "pine" }));
    await adminApi.updateCabin("pine", { max_guests: 12 });

    expect(calls[0]?.url).toBe("/api/cabins/pine");
    expect(calls[0]?.init?.method).toBe("PUT");
    expect(JSON.parse(String(calls[0]?.init?.body))).toEqual({ max_guests: 12 });
  });
});
