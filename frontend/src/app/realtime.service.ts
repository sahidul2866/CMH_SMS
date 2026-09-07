import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

import { RealtimeEvent, RealtimeStatus } from './models';

@Injectable({ providedIn: 'root' })
export class RealtimeService {
  private readonly statusSubject = new BehaviorSubject<RealtimeStatus>('offline');
  readonly status$ = this.statusSubject.asObservable();

  connect(waitingRoom: string): Observable<RealtimeEvent> {
    return new Observable<RealtimeEvent>((subscriber) => {
      let socket: WebSocket | null = null;
      let reconnectTimer: number | null = null;
      let heartbeatTimer: number | null = null;
      let attempts = 0;
      let closedByClient = false;

      const clearTimers = () => {
        if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
        if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer);
        reconnectTimer = null;
        heartbeatTimer = null;
      };
      const open = () => {
        this.statusSubject.next(attempts ? 'recovering' : 'connecting');
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        socket = new WebSocket(
          `${protocol}//${window.location.host}/api/v1/realtime/waiting-rooms/${encodeURIComponent(waitingRoom)}`,
        );
        socket.onopen = () => {
          attempts = 0;
          this.statusSubject.next('connected');
          heartbeatTimer = window.setInterval(() => {
            if (socket?.readyState === WebSocket.OPEN) socket.send('ping');
          }, 15000);
        };
        socket.onmessage = (message) => {
          try { subscriber.next(JSON.parse(message.data) as RealtimeEvent); } catch { /* Ignore malformed events. */ }
        };
        socket.onerror = () => socket?.close();
        socket.onclose = (event) => {
          clearTimers();
          if (closedByClient) return;
          if (event.code === 4401) {
            this.statusSubject.next('offline');
            window.location.assign('/');
            return;
          }
          attempts += 1;
          this.statusSubject.next(attempts < 4 ? 'recovering' : 'offline');
          reconnectTimer = window.setTimeout(open, Math.min(1000 * 2 ** (attempts - 1), 10000));
        };
      };

      open();
      return () => {
        closedByClient = true;
        clearTimers();
        socket?.close();
        this.statusSubject.next('offline');
      };
    });
  }
}
