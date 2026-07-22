import { CommonModule } from '@angular/common';
import { Component, OnDestroy, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription, interval } from 'rxjs';

import { AppSetting, AuditEvent, DisplayState, Doctor, QueueReport, QueueToken, RealtimeStatus, View, WaitingRoom } from './models';
import { QueueApiService } from './queue-api.service';
import { RealtimeService } from './realtime.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent implements OnDestroy {
  private readonly api = inject(QueueApiService);
  private readonly realtime = inject(RealtimeService);
  private readonly refreshSubscription: Subscription;
  private realtimeSubscription?: Subscription;
  private statusSubscription?: Subscription;

  doctors: Doctor[] = [
    { id: 'dr-khan', name: 'Dr. Ayesha Khan', department: 'Medicine', room: '205', waitingRoom: 'WR-1' },
    { id: 'dr-rahman', name: 'Dr. Farhan Rahman', department: 'Cardiology', room: '312', waitingRoom: 'WR-2' },
    { id: 'dr-sultana', name: 'Dr. Nusrat Sultana', department: 'Paediatrics', room: '118', waitingRoom: 'WR-3' },
    { id: 'dr-chowdhury', name: 'Dr. Imran Chowdhury', department: 'Orthopaedics', room: '407', waitingRoom: 'WR-4' },
  ];
  waitingRooms: WaitingRoom[] = [
    { id: 'waiting-room-1', code: 'WR-1', name: 'Shared Waiting Room 1', floor: '2nd Floor', display_label: 'Waiting Room 1' },
    { id: 'waiting-room-2', code: 'WR-2', name: 'Shared Waiting Room 2', floor: '3rd Floor', display_label: 'Waiting Room 2' },
    { id: 'waiting-room-3', code: 'WR-3', name: 'Shared Waiting Room 3', floor: '1st Floor', display_label: 'Waiting Room 3' },
    { id: 'waiting-room-4', code: 'WR-4', name: 'Shared Waiting Room 4', floor: '4th Floor', display_label: 'Waiting Room 4' },
  ];

  view: View = 'reception';
  selectedDoctorId = this.doctors[0].id;
  selectedWaitingRoom = 'WR-1';
  tokens: QueueToken[] = [];
  displayState: DisplayState | null = null;
  report: QueueReport | null = null;
  auditEvents: AuditEvent[] = [];
  settings: AppSetting[] = [];
  busy = false;
  message = '';
  lastSpokenTokenId = '';
  realtimeStatus: RealtimeStatus = 'offline';
  form = { patient_name: '', patient_phone: '', service_category: 'army', rank: '', service_number: '', source: 'walk_in', priority: 'normal' };

  constructor() {
    const requestedView = new URLSearchParams(window.location.search).get('view');
    if (requestedView === 'doctor' || requestedView === 'reports' || requestedView === 'settings' || requestedView === 'display') this.view = requestedView;
    this.refresh();
    this.api.listDoctors().subscribe({
      next: (doctors) => {
        if (!doctors.length) return;
        this.doctors = doctors;
        if (!doctors.some((doctor) => doctor.id === this.selectedDoctorId)) this.selectedDoctorId = doctors[0].id;
        this.doctorChanged();
      },
    });
    this.api.listWaitingRooms().subscribe({ next: (rooms) => { if (rooms.length) this.waitingRooms = rooms; } });
    this.refreshSubscription = interval(5000).subscribe(() => this.refresh());
    this.statusSubscription = this.realtime.status$.subscribe((status) => this.realtimeStatus = status);
    if (this.view === 'display') this.connectRealtime();
    if (this.view === 'reports') { this.api.report().subscribe((report) => this.report = report); this.api.audit().subscribe((events) => this.auditEvents = events); }
    if (this.view === 'settings') this.api.settings().subscribe((settings) => this.settings = settings);
  }

  ngOnDestroy(): void {
    this.refreshSubscription.unsubscribe();
    this.realtimeSubscription?.unsubscribe();
    this.statusSubscription?.unsubscribe();
  }

  get selectedDoctor(): Doctor {
    return this.doctors.find((doctor) => doctor.id === this.selectedDoctorId) ?? this.doctors[0];
  }

  get waiting(): QueueToken[] {
    return this.tokens.filter((token) => token.status === 'waiting');
  }

  get current(): QueueToken | undefined {
    return this.tokens.find((token) => ['called', 'recalled', 'in_progress'].includes(token.status));
  }

  get activeQueue(): QueueToken[] { return this.tokens.filter((token) => ['waiting', 'called', 'recalled', 'skipped', 'in_progress'].includes(token.status)); }

  setView(view: View): void {
    this.view = view;
    this.message = '';
    this.refresh();
    if (view === 'display') this.connectRealtime();
    else this.realtimeSubscription?.unsubscribe();
    if (view === 'reports') { this.api.report().subscribe((report) => this.report = report); this.api.audit().subscribe((events) => this.auditEvents = events); }
    if (view === 'settings') this.api.settings().subscribe((settings) => this.settings = settings);
  }

  doctorChanged(): void {
    this.refresh();
    if (this.view === 'display') this.connectRealtime();
  }

  waitingRoomChanged(): void {
    this.refresh();
    this.connectRealtime();
  }

  createToken(): void {
    if (!this.form.patient_name.trim() || !this.form.patient_phone.trim()) {
      this.message = 'Patient name and mobile number are required.';
      return;
    }
    const doctor = this.selectedDoctor;
    this.busy = true;
    this.api.createToken({
      ...this.form,
      patient_name: this.form.patient_name.trim(),
      patient_phone: this.form.patient_phone.trim(),
      doctor_id: doctor.id,
      doctor_name: doctor.name,
      department: doctor.department,
      room_number: doctor.room,
      waiting_room: this.selectedWaitingRoom,
    }).subscribe({
      next: (token) => {
        this.message = `${token.token_number} generated and added to ${doctor.name}'s live queue.`;
        this.form.patient_name = '';
        this.form.patient_phone = '';
        this.form.rank = '';
        this.form.service_number = '';
        this.busy = false;
        this.refresh();
      },
      error: () => { this.message = 'Could not generate the token. Check that the API is running.'; this.busy = false; },
    });
  }

  callNext(): void {
    this.busy = true;
    this.api.callNext(this.selectedDoctorId).subscribe({
      next: (token) => this.afterCall(token),
      error: (error) => { this.message = error?.error?.detail || 'No waiting patient found.'; this.busy = false; },
    });
  }

  call(token: QueueToken): void {
    this.busy = true;
    this.api.call(this.selectedDoctorId, token.id).subscribe({
      next: (called) => this.afterCall(called),
      error: () => { this.message = 'Unable to call this patient.'; this.busy = false; },
    });
  }

  complete(token: QueueToken): void {
    this.api.action(this.selectedDoctorId, token.id, 'complete').subscribe({
      next: () => { this.message = `${token.token_number} completed.`; this.refresh(); },
      error: () => this.message = 'Unable to complete this consultation.',
    });
  }

  queueAction(token: QueueToken, action: string): void {
    const needsReason = ['skip', 'no_show', 'cancel'].includes(action);
    const reason = needsReason ? window.prompt(`Reason to ${action.replace('_', ' ')} ${token.token_number}:`)?.trim() : undefined;
    if (needsReason && !reason) return;
    this.api.action(this.selectedDoctorId, token.id, action, reason).subscribe({
      next: () => { this.message = `${token.token_number} ${action.replace('_', ' ')} recorded.`; this.refresh(); },
      error: (error) => this.message = error?.error?.detail || 'Action could not be completed.',
    });
  }

  togglePriority(token: QueueToken): void {
    const priority = token.priority === 'priority' ? 'normal' : 'priority';
    const reason = window.prompt(`Reason for ${priority} priority:`)?.trim();
    if (!reason) return;
    this.api.updatePriority(token.id, priority, reason).subscribe(() => this.refresh());
  }

  saveSetting(setting: AppSetting): void {
    this.api.saveSetting(setting.key, setting.value).subscribe({ next: () => this.message = `${setting.key} settings saved.`, error: () => this.message = 'Unable to save settings.' });
  }

  reportEntries(group?: Record<string, number>): [string, number][] { return Object.entries(group || {}).sort((a, b) => b[1] - a[1]); }

  canAction(token: QueueToken, action: string): boolean {
    const states: Record<string, string[]> = { start: ['called', 'recalled'], complete: ['in_progress'], skip: ['called', 'recalled'], recall: ['skipped', 'called', 'recalled'], no_show: ['called', 'recalled', 'skipped'], cancel: ['waiting', 'skipped', 'in_progress'] };
    return states[action]?.includes(token.status) || false;
  }

  refresh(): void {
    if (this.view === 'display') {
      this.api.display(this.selectedWaitingRoom).subscribe({ next: (state) => { this.displayState = state; this.speakDisplay(state); } });
      return;
    }
    this.api.listTokens(this.selectedDoctorId).subscribe({ next: (tokens) => this.tokens = tokens });
  }

  private afterCall(token: QueueToken): void {
    this.message = `${token.token_number} — ${token.patient_name} called to room ${token.room_number}.`;
    this.busy = false;
    this.refresh();
  }

  private connectRealtime(): void {
    this.realtimeSubscription?.unsubscribe();
    this.realtimeSubscription = this.realtime.connect(this.selectedWaitingRoom).subscribe((event) => {
      if (event.type === 'patient.called') {
        // Fetch this display's room-specific queue while retaining the global call.
        this.refresh();
        return;
      }
      if (!event.display) return;
      this.displayState = event.display;
      this.speakDisplay(event.display);
    });
  }

  realtimeLabel(): string {
    return ({ connected: 'Realtime connected', connecting: 'Connecting realtime', recovering: 'Reconnecting', offline: 'Polling fallback' })[this.realtimeStatus];
  }

  serviceLabel(category: string): string {
    return ({ army: 'Bangladesh Army', navy: 'Bangladesh Navy', air_force: 'Bangladesh Air Force', retired: 'Retired', dependant: 'Service dependant', civilian: 'Civilian' } as Record<string, string>)[category] || category;
  }

  private speakDisplay(state: DisplayState): void {
    if (!state.current || state.current.id === this.lastSpokenTokenId || !('speechSynthesis' in window)) return;
    this.lastSpokenTokenId = state.current.id;
    const token = state.current;
    const utterance = new SpeechSynthesisUtterance(
      `Attention please. ${token.patient_name}, token ${token.token_number}. Doctor ${token.doctor_name}, room ${token.room_number}.`
    );
    utterance.lang = 'en-BD';
    utterance.rate = 0.88;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  }
}
