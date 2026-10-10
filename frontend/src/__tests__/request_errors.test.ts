import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, getApiKey, setApiKey } from "@/lib/api";

afterEach(() => {
  vi.unstubAllGlobals();
  setApiKey(null);
});

describe("request error handling", () => {
  it("maps a network failure to an actionable ApiError with status 0", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await api.get("/me").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
    expect(String((err as ApiError).detail)).toMatch(/Cannot reach the GitPulse API/);
  });

  it("keeps the session when the server returns a 5xx", async () => {
    setApiKey("test-key-123");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "internal server error" }), { status: 500 })),
    );
    await expect(api.get("/dashboard/overview")).rejects.toMatchObject({ status: 500 });
    expect(getApiKey()).toBe("test-key-123");
  });

  it("ends the session on 401", async () => {
    setApiKey("stale-key-123");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "invalid API key" }), { status: 401 })));
    await expect(api.get("/me")).rejects.toMatchObject({ status: 401 });
    expect(getApiKey()).toBeNull();
  });
});
