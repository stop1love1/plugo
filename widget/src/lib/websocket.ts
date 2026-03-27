export type MessageHandler = {
  onToken: (token: string) => void;
  onStart: () => void;
  onEnd: () => void;
  onError: (error: string) => void;
  onConnected: (data: any) => void;
};

export class PlugoWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: MessageHandler;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  constructor(url: string, handlers: MessageHandler) {
    this.url = url;
    this.handlers = handlers;
  }

  connect() {
    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          switch (data.type) {
            case "connected":
              this.handlers.onConnected(data);
              break;
            case "start":
              this.handlers.onStart();
              break;
            case "token":
              this.handlers.onToken(data.content);
              break;
            case "end":
              this.handlers.onEnd();
              break;
            case "error":
              this.handlers.onError(data.message);
              break;
          }
        } catch (e) {
          console.error("[Plugo] Failed to parse message:", e);
        }
      };

      this.ws.onclose = () => {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);
          setTimeout(() => this.connect(), delay);
        }
      };

      this.ws.onerror = (error) => {
        console.error("[Plugo] WebSocket error:", error);
      };
    } catch (e) {
      console.error("[Plugo] Failed to connect:", e);
    }
  }

  send(message: string, pageContext: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(
        JSON.stringify({
          message,
          pageContext,
        })
      );
    }
  }

  disconnect() {
    this.maxReconnectAttempts = 0; // Prevent reconnection
    this.ws?.close();
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
