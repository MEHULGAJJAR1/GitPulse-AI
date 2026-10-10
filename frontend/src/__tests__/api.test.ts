import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, setApiKey } from "@/lib/api";

describe("api client", () => {
  beforeEach(() => setApiKey("test-key-123"));
  afterEach(() => {
    setApiKey(null);
    vi.unstubAllGlobals();
  });

  it("sends the key in the X-API-Key header and never in the URL", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ role: "viewer" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const me = await api.get<{ role: string }>("/me");
    expect(me.role).toBe("viewer");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/me");
    expect((init.headers as Record<string, string>)["X-API-Key"]).toBe("test-key-123");
    expect(url).not.toContain("test-key");
  });

  it("raises ApiError with the server detail and clears the key on 401", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "invalid API key" }), { status: 401 })));
    await expect(api.get("/me")).rejects.toMatchObject({ status: 401, message: "invalid API key" });
    expect(sessionStorage.getItem("gitpulse.apiKey")).toBeNull();
    expect(new ApiError(500, "x")).toBeInstanceOf(Error);
  });
});
