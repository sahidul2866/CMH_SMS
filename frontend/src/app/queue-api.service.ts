import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';

import { AppSetting, AuditEvent, DisplayState, Doctor, QueueReport, QueueToken, WaitingRoom } from './models';

@Injectable({ providedIn: 'root' })
export class QueueApiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = 'http://localhost:8100/api/v1';

  createToken(payload: Record<string, string>) {
    return this.http.post<QueueToken>(`${this.baseUrl}/tokens`, payload);
  }

  listDoctors() {
    return this.http.get<Doctor[]>(`${this.baseUrl}/doctors`);
  }

  listWaitingRooms() {
    return this.http.get<WaitingRoom[]>(`${this.baseUrl}/waiting-rooms`);
  }

  listTokens(doctorId: string) {
    return this.http.get<QueueToken[]>(`${this.baseUrl}/tokens`, { params: { doctor_id: doctorId } });
  }

  callNext(doctorId: string) {
    return this.http.post<QueueToken>(`${this.baseUrl}/doctors/${doctorId}/call-next`, {});
  }

  call(doctorId: string, tokenId: string) {
    return this.http.post<QueueToken>(`${this.baseUrl}/doctors/${doctorId}/tokens/${tokenId}/call`, {});
  }

  complete(doctorId: string, tokenId: string) {
    return this.http.post<QueueToken>(`${this.baseUrl}/doctors/${doctorId}/tokens/${tokenId}/complete`, {});
  }

  action(doctorId: string, tokenId: string, action: string, reason?: string) {
    return this.http.post<QueueToken>(`${this.baseUrl}/doctors/${doctorId}/tokens/${tokenId}/action`, { action, reason: reason || null, actor: 'doctor.console' });
  }

  updatePriority(tokenId: string, priority: string, reason: string) {
    return this.http.patch<QueueToken>(`${this.baseUrl}/tokens/${tokenId}/priority`, { priority, reason, actor: 'reception.operator' });
  }

  report() { return this.http.get<QueueReport>(`${this.baseUrl}/reports/queue-summary`); }
  audit() { return this.http.get<AuditEvent[]>(`${this.baseUrl}/audit`); }
  settings() { return this.http.get<AppSetting[]>(`${this.baseUrl}/settings`); }
  saveSetting(key: string, value: Record<string, any>) { return this.http.put<AppSetting>(`${this.baseUrl}/settings/${key}`, { value }); }

  display(waitingRoom: string) {
    return this.http.get<DisplayState>(`${this.baseUrl}/displays/${waitingRoom}`);
  }
}
