import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { PlugoWebSocket, type Citation } from "./websocket";

describe("PlugoWebSocket", () => {
  it("should be importable", async () => {
    const mod = await import("./websocket");
    expect(mod.PlugoWebSocket).toBeDefined();
  });
});

describe("PlugoWebSocket citations event", () => {
  let OriginalWebSocket: typeof WebSocket;

  beforeEach(() => {
    OriginalWebSocket = globalThis.WebSocket;
  });

  afterEach(() => {
    globalThis.WebSocket = OriginalWebSocket;
  });

  it("forwards citations payload to onCitations handler", () => {
    // Minimal stub that captures assigned event handlers so we can invoke them.
    const instance: {
      readyState: number;
      send: ReturnType<typeof vi.fn>;
      close: ReturnType<typeof vi.fn>;
      onopen: (() => void) | null;
      onmessage: ((e: { data: string }) => void) | null;
      onclose: (() => void) | null;
      onerror: (() => void) | null;
    } = {
      readyState: 1,
      send: vi.fn(),
      close: vi.fn(),
      onopen: null,
      onmessage: null,
      onclose: null,
      onerror: null,
    };
    // @ts-expect-error — test stub, not a full WebSocket
    globalThis.WebSocket = vi.fn(() => instance);
    // OPEN constant is read at runtime; keep it consistent.
    // @ts-expect-error — writing static on stub
    globalThis.WebSocket.OPEN = 1;

    const onCitations = vi.fn();
    const ws = new PlugoWebSocket(
      "ws://localhost:8000/ws/chat/test-token",
      {
        onToken: vi.fn(),
        onStart: vi.fn(),
        onEnd: vi.fn(),
        onError: vi.fn(),
        onConnected: vi.fn(),
        onCitations,
      }
    );
    ws.connect();

    const payload: Citation[] = [
      { url: "https://example.com/a", title: "A", score: 0.9 },
      { url: "https://example.com/b", title: "B", score: 0.7 },
    ];
    // Simulate a citations event from the server.
    instance.onmessage?.({
      data: JSON.stringify({ type: "citations", items: payload }),
    });

    expect(onCitations).toHaveBeenCalledTimes(1);
    expect(onCitations).toHaveBeenCalledWith(payload);
  });
});
