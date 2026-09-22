import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

import { RealtimeEvent, RealtimeStatus } from './models';

@Injectable({ providedIn: 'root' })
export class RealtimeService {
  private readonly statusSubject = new BehaviorSubject<RealtimeStatus>('offline');
  readonly status$ = this.statusSubject.asObservable();

  connect(): Observable<RealtimeEvent> {
    return new Observable<RealtimeEvent>((subscriber) => {
      let socket: WebSocket | null = null;
      let reconnectTimer: number | null = null;
      let heartbeatTimer: number | null = null;
      let attempts = 0;
      let closedByClient = false;
      let lastMessage = Date.now();

      const clearTimers = () => {
        if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
        if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer);
        reconnectTimer = null;
        heartbeatTimer = null;
      };
      const open = () => {
        if (closedByClient) return;
        this.statusSubject.next(attempts ? 'recovering' : 'connecting');
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const connection = new WebSocket(`${protocol}//${window.location.host}/api/v1/realtime/updates`);
        socket = connection;
        connection.onopen = () => {
          lastMessage = Date.now();
          heartbeatTimer = window.setInterval(() => {
            if (Date.now() - lastMessage > 45000) { connection.close(); return; }
            if (connection.readyState === WebSocket.OPEN) connection.send('ping');
          }, 15000);
        };
        connection.onmessage = (message) => {
          if (closedByClient || socket !== connection) return;
          try {
            const event = JSON.parse(message.data) as RealtimeEvent;
            lastMessage = Date.now();
            if (event.type === 'connection.ready') {
              attempts = 0;
              this.statusSubject.next('connected');
            }
            subscriber.next(event);
          } catch { /* Ignore malformed events. */ }
        };
        connection.onerror = () => connection.close();
        connection.onclose = (event) => {
          if (socket !== connection) return;
          clearTimers();
          if (closedByClient) return;
          if (event.code === 4401 || event.code === 4403) {
            this.statusSubject.next('offline');
            if (event.code === 4401) window.location.assign('/');
            return;
          }
          attempts += 1;
          this.statusSubject.next(attempts < 4 ? 'recovering' : 'offline');
          const delay = Math.min(1000 * 2 ** Math.min(attempts - 1, 5), 30000);
          reconnectTimer = window.setTimeout(open, delay + Math.random() * delay * 0.2);
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
