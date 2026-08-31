import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, qs } from "./client";

describe("qs", () => {
  it("serialises defined params and skips empty ones", () => {
    expect(qs({ range: "7d", page: 1, live: true })).toBe("?range=7d&page=1&live=true");
    expect(qs({ a: undefined, b: null, c: "" })).toBe("");
    expect(qs({ status: "error", provider: undefined })).toBe("?status=error");
  });
});

describe("apiFetch", () => {
  afterEach(() => vi.unstubAllGlobals());

  const stubFetch = (impl: (url: string, init?: RequestInit) => Response | Promise<Response>) =>
    vi.stubGlobal("fetch", vi.fn(impl));

  it("returns parsed JSON on 2xx", async () => {
    stubFetch(() => new Response(JSON.stringify({ email: "a@b.c" }), { status: 200 }));
    await expect(apiFetch("/v1/auth/me")).resolves.toEqual({ email: "a@b.c" });
  });

  it("sends credentials and a JSON content-type", async () => {
    const spy = vi.fn((_url: string, _init?: RequestInit) => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", spy);
    await apiFetch("/v1/x", { method: "POST", body: "{}" });
    const init = spy.mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe("include");
    expect((init.headers as Record<string, string>)["content-type"]).toBe("application/json");
  });

  it("unwraps the {error:{type,message}} envelope into a typed ApiError", async () => {
    stubFetch(
      () =>
        new Response(JSON.stringify({ error: { type: "bad_range", message: "from > to" } }), {
          status: 400,
        }),
    );
    const err = (await apiFetch("/v1/usage/summary").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.type).toBe("bad_range");
    expect(err.message).toBe("from > to");
  });

  it("falls back to http_error when the body is not an envelope", async () => {
    stubFetch(() => new Response("nope", { status: 502, statusText: "Bad Gateway" }));
    const err = (await apiFetch("/v1/x").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.type).toBe("http_error");
    expect(err.status).toBe(502);
  });

  it("treats 204 as an empty body", async () => {
    stubFetch(() => new Response(null, { status: 204 }));
    await expect(apiFetch("/v1/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });
});
