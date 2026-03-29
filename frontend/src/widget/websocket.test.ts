import { describe, it, expect } from "vitest";

describe("PlugoWebSocket", () => {
  it("should be importable", async () => {
    const mod = await import("./websocket");
    expect(mod.PlugoWebSocket).toBeDefined();
  });
});
