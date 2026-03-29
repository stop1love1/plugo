export type ConnectionState = "connecting" | "connected" | "reconnecting" | "disconnected";

export type MessageHandler = {
  onToken: (token: string) => void;
  onStart: () => void;
  onEnd: (data?: any) => void;
  onError: (error: string) => void;
  onConnected: (data: any) => void;
  onConnectionChange?: (state: ConnectionState) => void;
};

export class PlugoWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: MessageHandler;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private sessionId: string | null = null;
  private visitorId: string | null = null;
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private _connectionState: ConnectionState = "disconnected";

  constructor(url: string, handlers: MessageHandler, sessionId?: string | null, visitorId?: string | null) {
    this.url = url;
    this.handlers = handlers;
    this.sessionId = sessionId || null;
    this.visitorId = visitorId || null;
  }

  private setConnectionState(state: ConnectionState) {
    this._connectionState = state;
    this.handlers.onConnectionChange?.(state);
  }

  connect() {
    try {
      this.setConnectionState(this.reconnectAttempts > 0 ? "reconnecting" : "connecting");
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.setConnectionState("connected");
        this.startPing();
        // Send init message with session_id and visitor_id
        this.ws?.send(
          JSON.stringify({
            type: "init",
            session_id: this.sessionId,
            visitor_id: this.visitorId,
          })
        );
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          switch (data.type) {
            case "connected":
              // Store the session_id for future reconnections
              if (data.session_id) {
                this.sessionId = data.session_id;
              }
              this.handlers.onConnected(data);
              break;
            case "start":
              this.handlers.onStart();
              break;
            case "token":
              this.handlers.onToken(data.content);
              break;
            case "end":
              this.handlers.onEnd(data);
              break;
            case "error":
              this.handlers.onError(data.message);
              break;
            case "pong":
              // Heartbeat acknowledged — connection is alive
              break;
          }
        } catch (e) {
          console.error("[Plugo] Failed to parse message:", e);
        }
      };

      this.ws.onclose = () => {
        this.stopPing();
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          this.setConnectionState("reconnecting");
          const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);
          setTimeout(() => this.connect(), delay);
        } else {
          this.setConnectionState("disconnected");
        }
      };

      this.ws.onerror = () => {
        // onclose will fire after onerror, handling reconnect there
      };
    } catch (e) {
      this.setConnectionState("disconnected");
      console.error("[Plugo] Failed to connect:", e);
    }
  }

  send(message: string, pageContext: any): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(
        JSON.stringify({
          message,
          pageContext,
        })
      );
      return true;
    }
    return false;
  }

  disconnect() {
    this.maxReconnectAttempts = 0; // Prevent reconnection
    this.stopPing();
    this.ws?.close();
    this.setConnectionState("disconnected");
  }

  private startPing() {
    this.stopPing();
    this.pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
  }

  private stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  get connectionState(): ConnectionState {
    return this._connectionState;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  getSessionId(): string | null {
    return this.sessionId;
  }
}
