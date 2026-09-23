import { HttpBackend, HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { ErrorHandler, Injectable, inject } from '@angular/core';
import { catchError, throwError, timeout } from 'rxjs';

type Diagnostic = { event: string; level?: string; [key: string]: unknown };

@Injectable({ providedIn: 'root' })
export class ClientLogService {
  // Bypass interceptors: a telemetry failure must never generate more telemetry.
  private readonly http = new HttpClient(inject(HttpBackend));
  private pending: Diagnostic[] = [];
  private timer: ReturnType<typeof setTimeout> | undefined;
  private sending = false;
  private cooldown = 0;
  private readonly recent = new Map<string, number>();
  private started = false;

  start(): void {
    if (this.started) return;
    this.started = true;
    window.addEventListener('error', event => this.error(event.error));
    window.addEventListener('unhandledrejection', event => this.error(event.reason));
    for (const state of ['online', 'offline']) {
      window.addEventListener(state, () => this.record({ event: 'network_state', state }));
    }
    window.addEventListener('popstate', () => this.navigation());
    this.navigation();
  }

  navigation(): void {
    const view = new URLSearchParams(window.location.search).get('view') || '';
    this.record({ event: 'navigation', view: /^[a-z-]{0,32}$/.test(view) ? view : '' });
  }

  error(error: unknown): void {
    const value = error instanceof Error ? error : null;
    const errorType = value?.name || 'UnknownError';
    const frames = (value?.stack || '').split('\n').slice(1).flatMap(line => {
      const match = line.match(/\/([A-Za-z0-9_.-]{1,120}):(\d+):(\d+)\)?$/);
      return match ? [{ file: match[1], line: Math.min(Number(match[2]), 10000000), column: Math.min(Number(match[3]), 10000000) }] : [];
    }).slice(0, 12);
    this.record({ event: 'error', level: 'error', error_type: /^[A-Za-z0-9_$.-]{1,80}$/.test(errorType) ? errorType : 'Error', error_code: value?.message.match(/\bNG\d+\b/)?.[0] || '', frames });
  }

  record(event: Diagnostic): void {
    if (document.documentElement.dataset['demo'] === 'true') return;
    const now = Date.now();
    const key = JSON.stringify(event);
    if (now - (this.recent.get(key) ?? -Infinity) < 10000) return;
    for (const [entry, timestamp] of this.recent) if (now - timestamp >= 10000) this.recent.delete(entry);
    if (this.recent.size >= 100) this.recent.delete(this.recent.keys().next().value!);
    this.recent.set(key, now);
    this.pending.push(event);
    if (this.pending.length > 50) this.pending.shift();
    this.schedule();
  }

  private schedule(): void {
    if (this.timer || this.sending || Date.now() < this.cooldown || !this.pending.length) return;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      this.sending = true;
      const events = this.pending.splice(0, 20);
      this.http.post('/api/v1/client-events', { events }).pipe(timeout(15000)).subscribe({
        next: () => { this.sending = false; this.schedule(); },
        error: () => { this.sending = false; this.pending = []; this.cooldown = Date.now() + 30000; },
      });
    }, 1000);
  }
}

@Injectable()
export class ApplicationErrorHandler implements ErrorHandler {
  private readonly logs = inject(ClientLogService);
  handleError(error: unknown): void { this.logs.error(error); console.error(error); }
}

export const clientLogInterceptor: HttpInterceptorFn = (request, next) => {
  const logs = inject(ClientLogService);
  return next(request).pipe(catchError((error: unknown) => {
    const url = new URL(request.url, window.location.origin);
    if (error instanceof HttpErrorResponse && url.origin === window.location.origin && url.pathname.startsWith('/api/v1/') && url.pathname !== '/api/v1/client-events') {
      logs.record({ event: 'http_failed', level: 'error', endpoint: url.pathname, status: error.status, request_id: error.headers.get('X-Request-ID') || '' });
    }
    return throwError(() => error);
  }));
};
