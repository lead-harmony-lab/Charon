export interface CharonWSFrame {
  event_type: string;
  timestamp?: string;
  task_id?: string;
  client_id?: string;
  agent_name?: string;
  data?: any;
  payload?: {
    text?: string;
    avatar_state?: ConciergeAvatarState;
    hud_overlay?: {
      pointer_target?: string;
      [key: string]: any;
    };
    [key: string]: any;
  } | any;
}

export interface ConciergeAvatarState {
  state?: string;
  emotion?: string;
  subtext?: string;
  [key: string]: any;
}

type MessageCallback = (frame: CharonWSFrame) => void;

export class CharonStream {
  private ws: WebSocket | null = null;
  private listeners: Map<string, Set<MessageCallback>> = new Map();
  private reconnectTimer: any = null;
  private heartbeatTimer: any = null;
  private apiKey: string = '';

  public connect(apiKey: string) {
    this.apiKey = apiKey;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/v1/ws?api_key=${encodeURIComponent(apiKey)}`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      this.emitToSubscribers('connection_status', { event_type: 'connection_status', data: { connected: true } });
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      try {
        const frame: CharonWSFrame = JSON.parse(event.data);
        if (frame.event_type) {
          this.emitToSubscribers(frame.event_type, frame);
        }
        this.emitToSubscribers('*', frame);
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    this.ws.onclose = () => {
      this.stopHeartbeat();
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
    this.stopHeartbeat();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.ws) this.ws.close();
  }

  private emitToSubscribers(eventType: string, frame: CharonWSFrame) {
    const callbacks = this.listeners.get(eventType);
    if (callbacks) {
      callbacks.forEach((cb) => cb(frame));
    }
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 5000);
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      if (this.apiKey) this.connect(this.apiKey);
    }, 3000);
  }
}

export const wsClient = new CharonStream();
