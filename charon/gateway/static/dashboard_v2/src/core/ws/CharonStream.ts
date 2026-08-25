/**
 * @file src/core/ws/CharonStream.ts
 * @description
 */
export interface CharonWSFrame {
  event_type?: string;
  type?: string; // Added to match CLI flexibility
  timestamp?: string;
  task_id?: string;
  client_id?: string;
  agent_name?: string;
  active_agent?: string; // CLI uses active_agent
  data?: any;
  payload?: any;
  [key: string]: any; // Allow flat payloads
}

type MessageCallback = (frame: CharonWSFrame) => void;

// src/core/ws/CharonStream.ts

export class CharonStream {
  private ws: WebSocket | null = null;
  private listeners: Map<string, Set<MessageCallback>> = new Map();
  private reconnectTimer: any = null;
  private apiKey: string = '';
  private clientId: string = 'dashboard_ui';

  // Add this getter to expose the connected client ID
  public getClientId(): string {
    return this.clientId;
  }

  public connect(apiKey: string, clientId: string = 'dashboard_ui') {
    this.apiKey = apiKey;
    this.clientId = clientId;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    // Fix: Add client_id to the query params just like the CLI
    const wsUrl = `${protocol}//${host}/v1/ws?client_id=${encodeURIComponent(this.clientId)}&api_key=${encodeURIComponent(apiKey)}`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      this.emitToSubscribers('connection_status', { event_type: 'connection_status', data: { connected: true } });
    };

    this.ws.onmessage = (event) => {
      try {
        const frame: CharonWSFrame = JSON.parse(event.data);

        // Fix: Fallback to 'type' if 'event_type' is missing
        const eventType = frame.event_type || frame.type;

        if (eventType) {
          this.emitToSubscribers(eventType, frame);
        }
        this.emitToSubscribers('*', frame);
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    this.ws.onclose = () => {
      this.emitToSubscribers('connection_status', { event_type: 'connection_status', data: { connected: false } });
      this.scheduleReconnect();
    };

    this.ws.onerror = (err) => {
      console.error('WebSocket error encountered:', err);
    };
  }

  public subscribe(eventType: string, callback: MessageCallback): () => void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(callback);

    return () => {
      const set = this.listeners.get(eventType);
      if (set) {
        set.delete(callback);
      }
    };
  }

  public disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.ws) this.ws.close();
  }

  public send(frame: CharonWSFrame) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const outFrame: CharonWSFrame = {
        client_id: this.clientId,
        ...frame
      };
      this.ws.send(JSON.stringify(outFrame));
    } else {
      console.warn(`[CharonStream] Cannot send ${frame.event_type || frame.type}: WebSocket is not open.`);
    }
  }

  private emitToSubscribers(eventType: string, frame: CharonWSFrame) {
    const callbacks = this.listeners.get(eventType);
    if (callbacks) {
      callbacks.forEach((cb) => cb(frame));
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      if (this.apiKey) this.connect(this.apiKey, this.clientId);
    }, 3000);
  }
}

export const wsClient = new CharonStream();