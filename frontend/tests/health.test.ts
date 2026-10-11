import { afterEach, describe, expect, it, vi } from "vitest";
import { getApiHealth } from "../src/lib/health";

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
describe("server dependency status", () => {
  it("fails closed when no internal API is configured", async () => {
    vi.stubEnv("API_INTERNAL_URL", "");
    expect(await getApiHealth()).toBe("unavailable");
  });
  it("recognizes a healthy backend", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok:true, json:async()=>({status:"ok"})}));
    expect(await getApiHealth()).toBe("ready");
  });
  it("does not mistake a dependency failure for readiness", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok:false}));
    expect(await getApiHealth()).toBe("unavailable");
  });
  it("handles network errors without exposing internal URLs", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("private endpoint")));
    expect(await getApiHealth()).toBe("unavailable");
  });
});
