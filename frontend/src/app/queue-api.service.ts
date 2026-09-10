import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';

import { MonthlySummary, PatientClassification, AppSetting, Appointment, AuditEvent, AuthUser, DeviceEndpoint, DisplayState, Doctor, Holiday, LookupOption, Patient, PermissionDefinition, QueueReport, QueueToken, RadiographyDashboard, ReceptionReportRow, RoleDefinition, ScheduleSlot, SmsMessage, WaitingRoom } from './models';

@Injectable({ providedIn: 'root' })
export class QueueApiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api/v1';

  login(username: string, password: string) {
    return this.http.post<AuthUser>(`${this.baseUrl}/auth/login`, { username, password });
  }
  session() { return this.http.get<AuthUser | null>(`${this.baseUrl}/auth/session`); }
  logout() { return this.http.post<void>(`${this.baseUrl}/auth/logout`, {}); }
  changePassword(currentPassword: string, newPassword: string) {
    return this.http.post<void>(`${this.baseUrl}/auth/password`, {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }
  users() { return this.http.get<AuthUser[]>(`${this.baseUrl}/users`); }
  createUser(payload: Record<string, string | null>) { return this.http.post<AuthUser>(`${this.baseUrl}/users`, payload); }
  updateUser(userId: string, payload: Record<string, unknown>) { return this.http.patch<AuthUser>(`${this.baseUrl}/users/${userId}`, payload); }
  resetUserPassword(userId: string, newPassword: string) { return this.http.post<void>(`${this.baseUrl}/users/${userId}/password`, { new_password: newPassword }); }
  deleteUser(userId: string) { return this.http.delete<void>(`${this.baseUrl}/users/${userId}`); }
  roles() { return this.http.get<RoleDefinition[]>(`${this.baseUrl}/roles`); }
  permissions() { return this.http.get<PermissionDefinition[]>(`${this.baseUrl}/permissions`); }
  createRole(payload: Record<string, unknown>) { return this.http.post<RoleDefinition>(`${this.baseUrl}/roles`, payload); }
  updateRole(name: string, payload: Record<string, unknown>) { return this.http.patch<RoleDefinition>(`${this.baseUrl}/roles/${name}`, payload); }
  deleteRole(name: string) { return this.http.delete<void>(`${this.baseUrl}/roles/${name}`); }
  lookups(includeInactive = false) { return this.http.get<LookupOption[]>(`${this.baseUrl}/lookups`, { params: includeInactive ? { include_inactive: true } : {} }); }
  createLookup(payload: Record<string, unknown>) { return this.http.post<LookupOption>(`${this.baseUrl}/lookups`, payload); }
  updateLookup(id: string, payload: Record<string, unknown>) { return this.http.patch<LookupOption>(`${this.baseUrl}/lookups/${id}`, payload); }
  holidays() { return this.http.get<Holiday[]>(`${this.baseUrl}/holidays`); }
  createHoliday(payload: Record<string, unknown>) { return this.http.post<Holiday>(`${this.baseUrl}/holidays`, payload); }
  devices() { return this.http.get<DeviceEndpoint[]>(`${this.baseUrl}/devices`); }
  createDevice(payload: Record<string, unknown>) { return this.http.post<{ device: DeviceEndpoint; client_key: string }>(`${this.baseUrl}/devices`, payload); }
  smsMessages() { return this.http.get<SmsMessage[]>(`${this.baseUrl}/notifications/sms`); }
  patients(query = '') { return this.http.get<Patient[]>(`${this.baseUrl}/patients`, { params: query ? { query } : {} }); }
  createPatient(payload: Record<string, unknown>) { return this.http.post<Patient>(`${this.baseUrl}/patients`, payload); }
  scheduleSlots(doctorId = '') { return this.http.get<ScheduleSlot[]>(`${this.baseUrl}/schedule-slots`, { params: doctorId ? { doctor_id: doctorId } : {} }); }
  appointments() { return this.http.get<Appointment[]>(`${this.baseUrl}/appointments`); }
  createAppointment(payload: Record<string, unknown>) { return this.http.post<Appointment>(`${this.baseUrl}/appointments`, payload); }
  updateAppointment(id: string, action: string, reason: string, slotId?: string) {
    return this.http.patch<Appointment>(`${this.baseUrl}/appointments/${id}`, { action, reason, slot_id: slotId || null });
  }
  checkInAppointment(id: string) { return this.http.post<QueueToken>(`${this.baseUrl}/appointments/${id}/check-in`, {}); }
  registrationPreview() { return this.http.get<{ serial_number: string; date: string }>(`${this.baseUrl}/registration-preview`); }

  createToken(payload: Record<string, string | number | null>) {
    return this.http.post<QueueToken>(`${this.baseUrl}/tokens`, payload);
  }

  updateWaitingPatient(id: string, payload: Record<string, string | number | null>) { return this.http.patch<QueueToken>(`${this.baseUrl}/tokens/${id}`, payload); }
  radiographerStatus() { return this.http.get<{id: string; name: string; room: string; occupied: boolean}[]>(`${this.baseUrl}/radiographers/status`); }
  createDoctor(payload: Record<string, unknown>) { return this.http.post(`${this.baseUrl}/admin/doctors`, payload); }
  removeDoctor(id: string) { return this.http.delete<void>(`${this.baseUrl}/admin/doctors/${id}`); }
  listDoctors() {
    return this.http.get<Doctor[]>(`${this.baseUrl}/doctors`);
  }

  updateDoctor(doctorId: string, payload: Record<string, unknown>) {
    return this.http.patch<{ id: string; room_number: string }>(`${this.baseUrl}/admin/doctors/${doctorId}`, payload);
  }

  listWaitingRooms() {
    return this.http.get<WaitingRoom[]>(`${this.baseUrl}/waiting-rooms`);
  }

  listTokens(doctorId: string, sharedWaiting = false) {
    return this.http.get<QueueToken[]>(`${this.baseUrl}/tokens`, { params: { doctor_id: doctorId, shared_waiting: sharedWaiting } });
  }

  callNext(doctorId: string) {
    return this.http.post<QueueToken>(`${this.baseUrl}/doctors/${doctorId}/call-next`, {});
  }

  call(doctorId: string, tokenId: string) {
    return this.http.post<QueueToken>(`${this.baseUrl}/doctors/${doctorId}/tokens/${tokenId}/call`, {});
  }

  action(doctorId: string, tokenId: string, action: string, reason?: string) {
    return this.http.post<QueueToken>(`${this.baseUrl}/doctors/${doctorId}/tokens/${tokenId}/action`, { action, reason: reason || null });
  }

  updatePriority(tokenId: string, priority: string, reason: string) {
    return this.http.patch<QueueToken>(`${this.baseUrl}/tokens/${tokenId}/priority`, { priority, reason });
  }
  updateTokenRoom(tokenId: string, roomNumber: string) {
    return this.http.patch<QueueToken>(`${this.baseUrl}/tokens/${tokenId}/room`, { room_number: roomNumber });
  }
  transferToken(tokenId: string, doctorId: string, reason: string) {
    return this.http.post<QueueToken>(`${this.baseUrl}/tokens/${tokenId}/transfer`, { doctor_id: doctorId, reason });
  }

  report() { return this.http.get<QueueReport>(`${this.baseUrl}/reports/queue-summary`); }
  dashboardPatients(status: string) { return this.http.get<QueueToken[]>(`${this.baseUrl}/dashboard/patients`, { params: { status } }); }
  availablePatients(doctorId: string) { return this.http.get<QueueToken[]>(`${this.baseUrl}/doctors/${doctorId}/available-patients`); }
  claimPatient(doctorId: string, tokenId: string) { return this.http.post<QueueToken>(`${this.baseUrl}/doctors/${doctorId}/claim/${tokenId}`, {}); }
  dashboard() { return this.http.get<RadiographyDashboard>(`${this.baseUrl}/dashboard`); }
  monthlySummary(params: Record<string, string>) { return this.http.get<MonthlySummary>(`${this.baseUrl}/reports/mri-summary`, { params }); }
  summaryPatients(params: Record<string, string>) { return this.http.get<QueueToken[]>(`${this.baseUrl}/reports/mri-summary/patients`, { params }); }
  summaryExport(format: 'xlsx' | 'pdf', params: Record<string, string>) { return this.http.get(`${this.baseUrl}/reports/mri-summary.${format}`, { params, responseType: 'blob' }); }
  correctClassification(id: string, payload: PatientClassification) { return this.http.patch<QueueToken>(`${this.baseUrl}/tokens/${id}/classification`, payload); }
  receptionReport(params: Record<string, string>) { return this.http.get<ReceptionReportRow[]>(`${this.baseUrl}/reports/reception`, { params }); }
  receptionReportExcel(params: Record<string, string>) { return this.http.get(`${this.baseUrl}/reports/reception.xlsx`, { params, responseType: 'blob', observe: 'response' }); }
  receptionReportPdf(params: Record<string, string>) { return this.http.get(`${this.baseUrl}/reports/reception.pdf`, { params, responseType: 'blob', observe: 'response' }); }
  audit() { return this.http.get<AuditEvent[]>(`${this.baseUrl}/audit`); }
  registrationFields() { return this.http.get<{fields: Record<string, string>; required: string[]}>(`${this.baseUrl}/registration-fields`); }
  saveRegistrationFields(required: string[]) { return this.http.put(`${this.baseUrl}/registration-fields`, {value: {required}}); }
  settings() { return this.http.get<AppSetting[]>(`${this.baseUrl}/settings`); }
  saveSetting(key: string, value: Record<string, any>) { return this.http.put<AppSetting>(`${this.baseUrl}/settings/${key}`, { value }); }
  testAnnouncement(value: Record<string, any>) { return this.http.post<{ status: string; voice_mode: string }>(`${this.baseUrl}/settings/announcement/test`, { value }); }

  display(waitingRoom: string) {
    return this.http.get<DisplayState>(`${this.baseUrl}/displays/${waitingRoom}`);
  }
}
