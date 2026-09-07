import { CommonModule } from '@angular/common';
import { Component, HostListener, OnDestroy, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription, interval } from 'rxjs';

import { MonthlySummary, PatientClassification, AppSetting, Appointment, AuditEvent, AuthUser, DeviceEndpoint, DisplayState, Doctor, Holiday, LookupOption, Patient, PermissionDefinition, QueueReport, QueueToken, RadiographyDashboard, RealtimeStatus, ReceptionReportRow, RoleDefinition, ScheduleSlot, SmsMessage, View, WaitingRoom } from './models';
import { QueueApiService } from './queue-api.service';
import { ModalComponent } from './modal.component';
import { RealtimeService } from './realtime.service';

const EMPTY_DOCTOR: Doctor = { id: '', name: 'No radiographer configured', department: '—', room: '—', waitingRoom: '' };
const TODAY_LOCAL = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const YEAR_START_LOCAL = `${TODAY_LOCAL.slice(0, 4)}-01-01`;

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, ModalComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent implements OnDestroy {
  private readonly api = inject(QueueApiService);
  private readonly realtime = inject(RealtimeService);
  private refreshSubscription?: Subscription;
  private realtimeSubscription?: Subscription;
  private statusSubscription?: Subscription;
  readonly isDemo = document.documentElement.dataset['demo'] === 'true';

  doctors: Doctor[] = [];
  waitingRooms: WaitingRoom[] = [];
  doctorRoomDrafts: Record<string, string> = {};
  tokenRoomDrafts: Record<string, string> = {};

  view: View = 'reception';
  selectedDoctorId = '';
  doctorOpened = false;
  previousView: View = 'dashboard';
  dashboardDetail = '';
  dashboardPatients: QueueToken[] = [];
  detailLoading = false;
  detailError = '';
  patientDetail: QueueToken | null = null;
  editor = '';
  editingSetting: AppSetting | null = null;
  editingDoctor: Doctor | null = null;
  editingUser: AuthUser | null = null;
  roleDraft: RoleDefinition | null = null;
  editingLookup: LookupOption | null = null;
  lookupVip = false;
  lookupWeight = 10;
  actionDialog: { token: QueueToken; action: string } | null = null;
  actionReason = '';
  actionDestination = '';
  actionPriority = '';
  actionBusy = false;
  claimCandidates: QueueToken[] = [];
  claimLoading = false;
  resetPasswordValue = '';
  toastTimer?: ReturnType<typeof setTimeout>;

  selectedWaitingRoom = '';
  tokens: QueueToken[] = [];
  displayState: DisplayState | null = null;
  report: QueueReport | null = null;
  dashboard: RadiographyDashboard | null = null;
  auditEvents: AuditEvent[] = [];
  reportTab: 'register' | 'summary' = 'register';
  summaryMonth = TODAY_LOCAL.slice(0, 7);
  summaryBasis = 'registrations';
  monthlySummary: MonthlySummary | null = null;
  summaryLoading = false;
  summaryExporting = false;
  summaryPatients: QueueToken[] | null = null;
  summaryPatientsTitle = '';
  classificationTarget: QueueToken | null = null;
  classificationDraft: PatientClassification = {};
  classificationSaving = false;
  classificationError = '';
  sponsorSearch = '';
  lookupReportGroup = '';
  lookupReportCode = '';
  reportGroups = [{value: 'officer', label: 'Officers / AFNS'}, {value: 'cadet', label: 'Officer / Nursing cadet'}, {value: 'jco', label: 'JCO'}, {value: 'or', label: 'OR / Recruit'}, {value: 'nce', label: 'NCE'}];
  reportCodes: Record<string, {value: string; label: string}[]> = {
    beneficiary_type: [{value: 'self', label: 'Self'}, {value: 'family', label: 'Family'}],
    service_status: [{value: 'serving', label: 'Serving'}, {value: 'retired', label: 'Retired'}],
    entitlement: [{value: 'military', label: 'Military'}, {value: 'civil', label: 'Civil entitled'}, {value: 're', label: 'RE'}, {value: 'cne', label: 'CNE'}],
  };

  classificationCode(field: string, value: string | null | undefined): string {
    const item = this.lookupOptions.find(option => option.category === field && option.value === value);
    return String(item?.metadata_json['report_code'] ?? value ?? '');
  }
  classificationChanged(draft: PatientClassification): void {
    if (this.classificationCode('beneficiary_type', draft.beneficiary_type) !== 'family') {
      draft.sponsor_rank = ''; draft.family_relationship = '';
    } else { draft.rank = ''; }
    if (this.classificationCode('entitlement', draft.entitlement) !== 'military') { draft.service_status = ''; draft.sponsor_rank = ''; }
  }
  sponsorRanks(selected: string | null | undefined): LookupOption[] {
    const search = this.sponsorSearch.toLowerCase();
    return this.lookup('rank_relationship').filter(item => item.value === selected || item.label.toLowerCase().includes(search));
  }
  loadMonthlySummary(): void {
    this.summaryLoading = true; this.monthlySummary = null; this.summaryPatients = null;
    this.api.monthlySummary({ month: this.summaryMonth, basis: this.summaryBasis }).subscribe({
      next: data => { this.monthlySummary = data; this.summaryLoading = false; },
      error: error => { this.message = this.apiErrorMessage(error, 'Could not load monthly summary.'); this.summaryLoading = false; }
    });
  }
  showSummaryPatients(day = '', category = ''): void {
    if (!this.monthlySummary) return;
    this.summaryPatientsTitle = `${day || this.monthlySummary.month} · ${this.monthlySummary.columns.find(col => col.key === category)?.label || (category === 'unclassified' ? 'Needs review' : 'All patients')}`;
    this.api.summaryPatients({ month: this.monthlySummary.month, basis: this.monthlySummary.basis, ...(day ? {day} : {}), ...(category ? {category} : {}) }).subscribe({
      next: rows => this.summaryPatients = rows,
      error: error => this.message = this.apiErrorMessage(error, 'Could not load patients.')
    });
  }
  exportMonthlySummary(format: 'xlsx' | 'pdf'): void {
    if (!this.monthlySummary) return;
    this.summaryExporting = true;
    const {month, basis} = this.monthlySummary;
    this.api.summaryExport(format, {month, basis}).subscribe({
      next: blob => { const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `mri-summary-${month}-${basis}.${format}`; anchor.click(); URL.revokeObjectURL(url); this.summaryExporting = false; },
      error: () => { this.message = 'Could not export the monthly summary.'; this.summaryExporting = false; }
    });
  }
  editClassification(patient: QueueToken): void {
    this.patientDetail = null; this.classificationTarget = patient; this.classificationError = ''; this.sponsorSearch = '';
    this.classificationDraft = {rank: patient.rank || '', beneficiary_type: patient.beneficiary_type || '', service_status: patient.service_status || '', entitlement: patient.entitlement || '', sponsor_rank: patient.sponsor_rank || '', family_relationship: patient.family_relationship || ''};
  }
  saveClassification(): void {
    if (!this.classificationTarget) return;
    this.classificationSaving = true;
    this.api.correctClassification(this.classificationTarget.id, this.classificationDraft).subscribe({
      next: patient => { this.classificationTarget = null; this.classificationSaving = false; this.patientDetail = patient; this.notify(patient.summary_category ? 'Report classification saved' : 'Saved · report category still needs review'); this.loadMonthlySummary(); this.loadReceptionReport(); this.refresh(); },
      error: error => { this.classificationError = this.apiErrorMessage(error, 'Could not save classification.'); this.classificationSaving = false; }
    });
  }
  receptionReportRows: ReceptionReportRow[] = [];
  reportFilters = { date_from: YEAR_START_LOCAL, date_to: TODAY_LOCAL, doctor_id: '', waiting_room: '', status: '', priority: '', service_category: '' };
  reportLoading = false;
  reportExporting = false;
  reportPdfExporting = false;
  settings: AppSetting[] = [];
  settingsTab: 'general' | 'account' | 'users' | 'roles' | 'master-data' | 'operations' = 'general';
  passwordForm = { current: '', next: '', confirm: '' };
  passwordBusy = false;
  audioTestBusy = false;
  busy = false;
  showReceptionModal = false;
  message = '';
  lastSpokenTokenId = '';
  realtimeStatus: RealtimeStatus = 'offline';
  currentUser: AuthUser | null = null;
  authChecked = false;
  loginBusy = false;
  loginError = '';
  showLoginPassword = false;
  isRefreshing = false;
  dataStatus: 'online' | 'offline' = 'online';
  lastSyncedAt: Date | null = null;
  loginForm = { username: '', password: '' };
  users: AuthUser[] = [];
  roles: RoleDefinition[] = [];
  permissionCatalog: PermissionDefinition[] = [];
  selectedRoleName = '';
  showRoleCreator = false;
  newRole = { name: '', display_name: '', access_profile: 'reception', description: '', permissions: [] as string[] };
  newUser = { username: '', full_name: '', password: '', role: 'reception', doctor_id: '' };
  form = { beneficiary_type: '', service_status: '', entitlement: '', sponsor_rank: '', family_relationship: '', patient_title: '', patient_name: '', patient_phone: '', service_category: 'civilian', rank: '', service_number: '', priority: 'normal', age: null as number | null, unit: '', mri_area: '', contrast: null as number | null, film: null as number | null, report: '', patient_source: '' };
  registrationSerial = '';
  registrationServerDate = '';
  openRegistration(): void {
    this.loadLookups();
    this.message = '';
    this.showReceptionModal = true;
    this.registrationSerial = '';
    this.api.registrationPreview().subscribe({
      next: preview => { this.registrationSerial = preview.serial_number; this.registrationServerDate = preview.date; },
      error: () => { this.message = 'Serial will be assigned when saved.'; },
    });
  }
  rankSearch = '';
  get registrationDate(): string { return new Intl.DateTimeFormat('en-CA').format(new Date()); }
  get filteredRanks(): LookupOption[] {
    return this.lookup('rank_relationship').filter(item => item.value === this.form.rank ||
      `${item.label} ${item.value}`.toLowerCase().includes(this.rankSearch.toLowerCase()));
  }
  printToken: QueueToken | null = null;
  lookupOptions: LookupOption[] = [];
  lookupCategories = ['department', 'room_number', 'sex', 'service_category', 'rank_relationship', 'priority_category', 'patient_source', 'beneficiary_type', 'service_status', 'entitlement', 'family_relationship'];
  selectedLookupCategory = 'patient_source';
  newLookup = { category: 'patient_source', value: '', label: '', sort_order: 0 };
  holidays: Holiday[] = [];
  newHoliday = { holiday_date: '', name: '' };
  devices: DeviceEndpoint[] = [];
  newDevice = { name: '', device_type: 'display', waiting_room: '' };
  smsMessages: SmsMessage[] = [];
  patients: Patient[] = [];
  appointments: Appointment[] = [];
  appointmentSlots: ScheduleSlot[] = [];
  allAppointmentSlots: ScheduleSlot[] = [];
  rescheduleSlots: Record<string, string> = {};
  patientSearch = '';
  appointmentDoctorId = '';
  appointmentForm = { patient_id: '', slot_id: '', reason: '', notes: '' };
  newPatient = { name: '', mobile: '', title: '', sex: '' };

  constructor() {
    if (this.isDemo) {
      this.authChecked = true;
      return;
    }
    this.api.session().subscribe({
      next: (user) => {
        this.currentUser = user;
        this.authChecked = true;
        if (user) this.initialize();
      },
      error: () => { this.authChecked = true; },
    });
  }

  private initialize(): void {
    // Initialization may run after both a restored session and an explicit login.
    // Keep exactly one polling timer so repeated initialization cannot multiply
    // background requests.
    this.refreshSubscription?.unsubscribe();
    const requestedView = new URLSearchParams(window.location.search).get('view');
    const defaultView: View = this.hasPermission('pages.dashboard') ? 'dashboard'
      : this.hasPermission('pages.radiographer') ? 'doctor'
      : this.hasPermission('pages.reception') ? 'reception'
      : this.hasPermission('pages.reports') ? 'reports'
      : this.hasPermission('pages.display') ? 'display'
      : 'settings';
    this.view = defaultView;
    if (requestedView === 'dashboard' || requestedView === 'reception' || requestedView === 'doctor' || requestedView === 'reports' || requestedView === 'reception-report' || requestedView === 'settings' || requestedView === 'display') {
      if (this.canView(requestedView)) this.view = requestedView;
    }
    this.dashboardDetail = this.view === 'dashboard' ? new URLSearchParams(location.search).get('detail') || '' : '';
    this.refresh();
    this.api.listDoctors().subscribe({
      next: (doctors) => {
        if (!doctors.length) return;
        this.doctors = doctors;
        this.setDoctorRoomDrafts();
        const assigned = this.currentUser?.doctor_id
          ? doctors.find((doctor) => doctor.id === this.currentUser?.doctor_id)
          : undefined;
        this.selectedDoctorId = assigned?.id || (doctors.some((doctor) => doctor.id === this.selectedDoctorId) ? this.selectedDoctorId : doctors[0].id);
        if (!doctors.some((doctor) => doctor.id === this.appointmentDoctorId)) this.appointmentDoctorId = doctors[0].id;
        this.doctorChanged();
      },
    });
    this.api.listWaitingRooms().subscribe({ next: (rooms) => {
      this.waitingRooms = rooms;
      if (!rooms.some((room) => room.code === this.selectedWaitingRoom)) this.selectedWaitingRoom = rooms[0]?.code || '';
      if (!this.newDevice.waiting_room) this.newDevice.waiting_room = rooms[0]?.code || '';
      if (this.view === 'display' && this.selectedWaitingRoom) {
        this.refresh();
        this.connectRealtime();
      }
    } });
    // Poll silently. Showing the global loading bar for every poll made the
    // page flash even when no queue data had changed.
    this.refreshSubscription = interval(2000).subscribe(() => this.refresh(false));
    this.statusSubscription = this.realtime.status$.subscribe((status) => this.realtimeStatus = status);
    if (this.view === 'display') this.connectRealtime();
    if (this.view === 'dashboard') this.loadDashboard();
    if (this.view === 'reports') { this.api.report().subscribe((report) => this.report = report); this.api.audit().subscribe((events) => this.auditEvents = events); }
    if (this.view === 'reception-report') this.loadReceptionReport();
    if (this.view === 'settings') this.loadSettings();
    if (this.hasPermission('users.view')) {
      this.api.users().subscribe((users) => this.users = users);
    }
    if (this.hasPermission('roles.view')) {
      this.api.roles().subscribe((roles) => {
        this.roles = roles;
        if (!roles.some((role) => role.name === this.selectedRoleName)) this.selectedRoleName = roles[0]?.name || '';
      });
      this.api.permissions().subscribe((permissions) => this.permissionCatalog = permissions);
    }
    this.loadLookups();
  }

  ngOnDestroy(): void {
    this.refreshSubscription?.unsubscribe();
    this.realtimeSubscription?.unsubscribe();
    this.statusSubscription?.unsubscribe();
  }

  login(): void {
    this.loginBusy = true;
    this.loginError = '';
    this.api.login(this.loginForm.username.trim(), this.loginForm.password).subscribe({
      next: (user) => {
        this.currentUser = user;
        this.loginBusy = false;
        this.loginForm.password = '';
        this.initialize();
      },
      error: (error) => {
        this.loginError = error?.error?.detail || 'Login failed.';
        this.loginBusy = false;
      },
    });
  }

  demoLogin(): void {
    this.currentUser = {
      id: 'demo-admin', username: 'demo-admin', full_name: 'Demo Administrator', role: 'Demo Admin',
      access_profile: 'reception', is_active: true,
      permissions: ['pages.dashboard', 'pages.reception', 'pages.radiographer', 'pages.display', 'pages.reports', 'dashboard.view', 'directory.view', 'master_data.view', 'queue.serial.create', 'queue.view', 'queue.call', 'queue.action', 'queue.priority', 'queue.transfer', 'queue.print', 'audio.announce', 'display.view', 'reports.view'],
    };
    this.initialize();
  }

  logout(): void {
    if (this.isDemo) { window.location.reload(); return; }
    this.api.logout().subscribe({ complete: () => window.location.reload() });
  }

  canView(view: View): boolean {
    if (!this.currentUser) return false;
    if (view === 'dashboard') return this.hasPermission('pages.dashboard') && this.hasPermission('dashboard.view');
    if (view === 'settings') return true;
    if (view === 'reception') return this.hasPermission('pages.reception');
    if (view === 'appointments') return false;
    if (view === 'doctor') return this.hasPermission('pages.radiographer');
    if (view === 'reports') return this.hasPermission('pages.reports');
    if (view === 'reception-report') return this.hasPermission('pages.reports');
    if (view === 'display') return this.hasPermission('pages.display');
    return false;
  }

  get isAdmin(): boolean {
    return (this.currentUser?.access_profile || this.currentUser?.role) === 'admin'
      || !!this.currentUser?.permissions?.includes('settings.manage');
  }

  hasPermission(permission: string): boolean {
    return (this.currentUser?.access_profile || this.currentUser?.role) === 'admin'
      || !!this.currentUser?.permissions?.includes(permission)
      || !!this.currentUser?.permissions?.includes('*');
  }

  get selectedRole(): RoleDefinition | undefined {
    return this.roles.find((role) => role.name === this.selectedRoleName);
  }

  loadDashboard(): void {
    this.api.dashboard().subscribe({
      next: (dashboard) => { this.dashboard = dashboard; this.markSynced(); },
      error: (error) => { this.message = error?.error?.detail || 'Could not load dashboard.'; this.markOffline(); },
    });
  }

  saveDoctorRoom(doctorId: string): void {
    const value = (this.doctorRoomDrafts[doctorId] ?? '').trim();
    if (!value) {
      this.message = 'Room number cannot be empty.';
      return;
    }
    this.api.updateDoctor(doctorId, { room_number: value }).subscribe({
      next: (updated) => {
        this.doctors = this.doctors.map((doctor) => doctor.id === updated.id ? { ...doctor, room: updated.room_number } : doctor);
        this.doctorRoomDrafts[updated.id] = updated.room_number;
        if (this.selectedDoctorId === updated.id) this.selectedDoctorId = updated.id;
        this.editor = '';
        this.notify(`Room updated to ${updated.room_number}.`);
      },
      error: (error) => {
        this.message = error?.error?.detail || 'Could not update room number.';
      },
    });
  }

  get permissionGroups(): string[] {
    return [...new Set(this.permissionCatalog.map((permission) => permission.group))];
  }

  permissionsForGroup(group: string): PermissionDefinition[] {
    return this.permissionCatalog.filter((permission) => permission.group === group);
  }

  canViewOperations(): boolean {
    return ['holidays.view', 'holidays.manage', 'devices.view', 'devices.manage', 'sms.view', 'sms.retry', 'directory.manage', 'doctor.room.manage']
      .some((permission) => this.hasPermission(permission));
  }

  createUser(): void {
    const payload = { ...this.newUser, doctor_id: this.roleProfile(this.newUser.role) === 'radiographer' ? this.newUser.doctor_id || null : null };
    this.api.createUser(payload).subscribe({
      next: (user) => {
        this.users = [...this.users, user].sort((a, b) => a.username.localeCompare(b.username));
        this.editor = '';
        this.newUser = { username: '', full_name: '', password: '', role: 'reception', doctor_id: '' };
        this.message = `${user.username} created.`;
      },
      error: (error) => this.message = error?.error?.detail || 'Could not create user.',
    });
  }

  roleProfile(name: string): string {
    return this.roles.find((role) => role.name === name)?.access_profile || name;
  }

  setDoctorRoomDrafts(): void {
    this.doctors.forEach((doctor) => {
      this.doctorRoomDrafts[doctor.id] = doctor.room;
    });
  }

  toggleUser(account: AuthUser): void {
    this.api.updateUser(account.id, { is_active: !account.is_active }).subscribe({
      next: (updated) => this.users = this.users.map((item) => item.id === updated.id ? updated : item),
      error: (error) => this.message = error?.error?.detail || 'Could not update account.',
    });
  }

  updateUserRole(account: AuthUser, role: string): void {
    const definition = this.roles.find((item) => item.name === role);
    const doctorId = definition?.access_profile === 'radiographer' ? account.doctor_id || null : null;
    this.api.updateUser(account.id, { role, doctor_id: doctorId }).subscribe({
      next: (updated) => this.users = this.users.map((item) => item.id === updated.id ? updated : item),
      error: (error) => this.message = error?.error?.detail || 'Could not assign role.',
    });
  }

  deleteUser(account: AuthUser): void {
    if (!window.confirm(`Delete account ${account.username}?`)) return;
    this.api.deleteUser(account.id).subscribe({
      next: () => this.users = this.users.filter((item) => item.id !== account.id),
      error: (error) => this.message = error?.error?.detail || 'Could not delete account.',
    });
  }

  createRole(): void {
    this.api.createRole(this.newRole).subscribe({
      next: (role) => {
        this.roles = [...this.roles, role].sort((a, b) => a.display_name.localeCompare(b.display_name));
        this.selectedRoleName = role.name;
        this.showRoleCreator = false;
        this.editor = '';
        this.newRole = { name: '', display_name: '', access_profile: 'reception', description: '', permissions: [] };
      },
      error: (error) => this.message = error?.error?.detail || 'Could not create role.',
    });
  }

  saveRole(role: RoleDefinition): void {
    this.api.updateRole(role.name, { display_name: role.display_name, access_profile: role.access_profile, description: role.description, permissions: role.permissions }).subscribe({
      next: updated => { this.roles = this.roles.map(item => item.name === updated.name ? updated : item); this.editor = ''; this.notify('Role saved'); },
      error: (error) => this.message = error?.error?.detail || 'Could not save role.',
    });
  }

  toggleRolePermission(role: RoleDefinition, permission: string, enabled: boolean): void {
    role.permissions = enabled
      ? [...new Set([...role.permissions, permission])].sort()
      : role.permissions.filter((item) => item !== permission);
  }

  toggleNewRolePermission(permission: string, enabled: boolean): void {
    this.newRole.permissions = enabled
      ? [...new Set([...this.newRole.permissions, permission])].sort()
      : this.newRole.permissions.filter((item) => item !== permission);
  }

  deleteRole(role: RoleDefinition): void {
    if (!window.confirm(`Delete role ${role.display_name}?`)) return;
    this.api.deleteRole(role.name).subscribe({
      next: () => this.roles = this.roles.filter((item) => item.name !== role.name),
      error: (error) => this.message = error?.error?.detail || 'Could not delete role.',
    });
  }

  resetPassword(account: AuthUser): void {
    if (!this.hasPermission('users.password.reset')) return;
    this.editingUser = account; this.resetPasswordValue = ''; this.editor = 'reset-password';
  }

  submitResetPassword(): void {
    if (!this.editingUser || this.resetPasswordValue.length < 10) return;
    const account = this.editingUser;
    this.api.resetUserPassword(account.id, this.resetPasswordValue).subscribe({
      next: () => { this.editor = ''; this.resetPasswordValue = ''; this.notify(`Password updated for ${account.username}.`); },
      error: (error) => this.message = error?.error?.detail || 'Could not reset password.',
    });
  }

  get selectedDoctor(): Doctor {
    return this.doctors.find((doctor) => doctor.id === this.selectedDoctorId) ?? this.doctors[0] ?? EMPTY_DOCTOR;
  }

  get waiting(): QueueToken[] { return this.activeQueue.filter(token => token.status === 'waiting'); }

  get callableWaiting(): QueueToken[] { return this.waiting.filter((token) => token.priority !== 'vip'); }

  get current(): QueueToken | undefined {
    return this.tokens.find((token) => token.doctor_id === this.selectedDoctorId && ['called', 'recalled', 'in_progress'].includes(token.status));
  }

  get activeQueue(): QueueToken[] { return this.tokens.filter(token => ['waiting', 'called', 'recalled', 'skipped', 'in_progress'].includes(token.status)).sort((a, b) => Number(b.priority === 'vip') - Number(a.priority === 'vip') || Number(['called', 'recalled', 'in_progress'].includes(b.status)) - Number(['called', 'recalled', 'in_progress'].includes(a.status)) || a.created_at.localeCompare(b.created_at)); }
  get canTakePatient(): boolean { return this.hasPermission('queue.action') && !this.tokens.some(token => ['waiting', 'called', 'recalled', 'in_progress'].includes(token.status)); }

  trackToken(_: number, token: QueueToken): string { return token.id; }
  trackRadiographer(_: number, row: { doctor_id: string }): string { return row.doctor_id; }

  dashboardStatuses(data: RadiographyDashboard): { label: string; value: number; color: string }[] {
    const known = data.waiting + data.called + data.in_progress + data.completed;
    return [
      { label: 'Waiting', value: data.waiting, color: '#d6a900' },
      { label: 'Called', value: data.called, color: '#4f83b6' },
      { label: 'In service', value: data.in_progress, color: '#7a68a6' },
      { label: 'Completed', value: data.completed, color: '#2f7d5b' },
      { label: 'Other', value: Math.max(data.total - known, 0), color: '#a7b4af' },
    ].filter((item) => item.value > 0);
  }

  dashboardDonut(data: RadiographyDashboard): string {
    if (!data.total) return 'conic-gradient(#e7eeeb 0deg 360deg)';
    let angle = 0;
    const stops = this.dashboardStatuses(data).map((item) => {
      const start = angle;
      angle += item.value / data.total * 360;
      return `${item.color} ${start}deg ${angle}deg`;
    });
    return `conic-gradient(${stops.join(',')})`;
  }

  dashboardVipStatuses(data: RadiographyDashboard): { label: string; value: number; color: string }[] {
    const known = data.vip_waiting + data.vip_active + data.vip_completed;
    return [
      { label: 'Waiting', value: data.vip_waiting, color: '#d6a900' },
      { label: 'Active', value: data.vip_active, color: '#8b6eae' },
      { label: 'Completed', value: data.vip_completed, color: '#2f7d5b' },
      { label: 'Other', value: Math.max(data.vip_total - known, 0), color: '#a7b4af' },
    ].filter((item) => item.value > 0);
  }

  dashboardVipDonut(data: RadiographyDashboard): string {
    if (!data.vip_total) return 'conic-gradient(#e7eeeb 0deg 360deg)';
    let angle = 0;
    const stops = this.dashboardVipStatuses(data).map((item) => {
      const start = angle;
      angle += item.value / data.vip_total * 360;
      return `${item.color} ${start}deg ${angle}deg`;
    });
    return `conic-gradient(${stops.join(',')})`;
  }

  dashboardVipWidth(vip: number, data: RadiographyDashboard): number {
    const maximum = Math.max(...data.radiographers.map((row) => row.vip), 1);
    return vip / maximum * 100;
  }

  dashboardPercent(value: number, total: number): number { return total ? Math.round(value / total * 100) : 0; }
  dashboardWorkloadWidth(total: number, data: RadiographyDashboard): number {
    const maximum = Math.max(...data.radiographers.map((row) => row.total), 1);
    return total / maximum * 100;
  }

  get missingTokenFields(): string[] {
    const missing: string[] = [];
    if (this.form.patient_name.trim().length < 2) missing.push('patient name');
    if (!this.form.patient_source) missing.push('patient source');
    if ([this.form.age, this.form.contrast, this.form.film].some(value => value !== null && (!Number.isInteger(value) || value < 0)) || (this.form.age !== null && this.form.age > 150)) missing.push('valid age, contrast and film numbers');
    return missing;
  }

  setView(view: View): void {
    if (!this.canView(view)) return;
    if (view === 'display' && this.view !== 'display') this.previousView = this.view;
    this.view = view;
    this.doctorOpened = false;
    this.dashboardDetail = '';
    this.message = '';
    const url = new URL(window.location.href);
    url.searchParams.set('view', view);
    url.searchParams.delete('detail');
    window.history.pushState({}, '', url);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    this.refresh();
    if (view === 'display') this.connectRealtime();
    else this.realtimeSubscription?.unsubscribe();
    if (view === 'reports') { this.api.report().subscribe((report) => this.report = report); this.api.audit().subscribe((events) => this.auditEvents = events); }
    if (view === 'reception-report') this.loadReceptionReport();
    if (view === 'settings') {
      this.settingsTab = this.hasPermission('settings.manage') ? 'general'
        : this.hasPermission('master_data.manage') ? 'master-data'
        : this.canViewOperations() ? 'operations'
        : 'account';
      this.loadSettings();
    }
  }

  private receptionReportParams(): Record<string, string> {
    return Object.fromEntries(Object.entries(this.reportFilters).filter(([, value]) => value));
  }

  loadReceptionReport(): void {
    this.reportLoading = true;
    this.api.receptionReport(this.receptionReportParams()).subscribe({
      next: (rows) => { this.receptionReportRows = rows; this.reportLoading = false; },
      error: (error) => { this.message = error?.error?.detail || 'Could not load the reception report.'; this.reportLoading = false; },
    });
  }

  exportReceptionReport(): void {
    this.reportExporting = true;
    this.api.receptionReportExcel(this.receptionReportParams()).subscribe({
      next: (response) => {
        const disposition = response.headers.get('content-disposition') || '';
        const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || 'reception-report.xlsx';
        const url = URL.createObjectURL(response.body!);
        const anchor = document.createElement('a');
        anchor.href = url; anchor.download = filename; anchor.click();
        URL.revokeObjectURL(url);
        this.reportExporting = false;
      },
      error: (error) => { this.message = error?.error?.detail || 'Could not create the Excel report.'; this.reportExporting = false; },
    });
  }

  exportReceptionReportPdf(): void {
    this.reportPdfExporting = true;
    this.api.receptionReportPdf(this.receptionReportParams()).subscribe({
      next: (response) => {
        const disposition = response.headers.get('content-disposition') || '';
        const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || 'reception-report.pdf';
        const url = URL.createObjectURL(response.body!);
        const anchor = document.createElement('a');
        anchor.href = url; anchor.download = filename; anchor.click();
        URL.revokeObjectURL(url);
        this.reportPdfExporting = false;
      },
      error: (error) => { this.message = error?.error?.detail || 'Could not create the PDF report.'; this.reportPdfExporting = false; },
    });
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
    const patientName = this.form.patient_name.trim();
    if (patientName.length < 2) {
      this.message = 'Patient name must contain at least 2 characters.';
      return;
    }
    if (this.missingTokenFields.length) return;
    this.busy = true;
    this.api.createToken({
      ...this.form,
      patient_title: this.form.patient_title || '',
      patient_name: patientName,
      patient_phone: this.form.patient_phone.trim(),
      rank: this.form.rank || '',
      service_number: this.form.service_number.trim(),
      doctor_id: null,
      doctor_name: '',
      department: '',
      room_number: '',
      waiting_room: '',
      source: 'walk_in',
    }).subscribe({
      next: (token) => {
        this.notify(`Patient added · ${token.serial_number || token.token_number}`);
        this.form.beneficiary_type = this.form.service_status = this.form.entitlement = this.form.sponsor_rank = this.form.family_relationship = this.sponsorSearch = '';
        this.form.priority = 'normal';
        this.form.patient_name = '';
        this.form.patient_phone = '';
        this.form.rank = '';
        this.form.service_number = '';
        this.form.age = this.form.contrast = this.form.film = null;
        this.form.unit = this.form.mri_area = this.form.report = this.form.patient_source = this.rankSearch = '';
        this.busy = false;
        this.showReceptionModal = false;
        this.refresh();
      },
      error: (error) => {
        this.message = this.apiErrorMessage(error, 'Could not generate the token.');
        this.busy = false;
      },
    });
  }

  private apiErrorMessage(error: any, fallback: string): string {
    const detail = error?.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map((item: any) => {
        const field = Array.isArray(item?.loc) ? item.loc.filter((part: unknown) => part !== 'body').join(' → ') : '';
        return `${field ? field.replaceAll('_', ' ') + ': ' : ''}${item?.msg || 'Invalid value'}`;
      }).join('. ');
    }
    return fallback;
  }

  printSlip(token: QueueToken): void {
    this.printToken = token;
    window.setTimeout(() => {
      window.print();
      this.printToken = null;
    });
  }

  loadLookups(): void {
    this.api.lookups(this.hasPermission('master_data.manage')).subscribe((items) => {
      this.lookupOptions = items;
      this.form.service_category ||= this.lookup('service_category')[0]?.value || '';
      this.form.priority ||= this.lookup('priority_category').find((item) => item.value === 'normal')?.value || this.lookup('priority_category')[0]?.value || '';
    });
  }

  lookup(category: string, activeOnly = true): LookupOption[] {
    return this.lookupOptions.filter((item) => item.category === category && (!activeOnly || item.is_active))
      .sort((a, b) => a.sort_order - b.sort_order || a.label.localeCompare(b.label));
  }

  lookupLabel(category: string, value?: string | null): string {
    if (!value) return '';
    return this.lookupOptions.find((item) => item.category === category && item.value === value)?.label || value;
  }

  createLookup(): void {
    this.newLookup.category = this.selectedLookupCategory;
    const label = this.newLookup.label.trim();
    const value = (this.newLookup.value.trim() || label).toLowerCase().replace(/[^a-z0-9._-]+/g, '_');
    if (!value || !label) return;
    this.api.createLookup({ ...this.newLookup, value, label, metadata_json: {} }).subscribe({
      next: (item) => {
        this.lookupOptions = [...this.lookupOptions, item];
        this.newLookup = { ...this.newLookup, value: '', label: '', sort_order: item.sort_order + 1 };
        this.message = `${item.label} added to ${item.category.replaceAll('_', ' ')}.`;
      },
      error: (error) => this.message = error?.error?.detail || 'Could not add dropdown value.',
    });
  }

  toggleLookup(item: LookupOption): void {
    this.api.updateLookup(item.id, { is_active: !item.is_active }).subscribe({
      next: (updated) => this.lookupOptions = this.lookupOptions.map((value) => value.id === updated.id ? updated : value),
      error: (error) => this.message = error?.error?.detail || 'Could not update dropdown value.',
    });
  }

  renameLookup(item: LookupOption): void {
    this.editingLookup = item;
    this.newLookup = { category: item.category, value: item.value, label: item.label, sort_order: item.sort_order };
    this.lookupReportGroup = String(item.metadata_json['report_group'] || '');
    this.lookupReportCode = String(item.metadata_json['report_code'] || item.value);
    this.lookupVip = item.metadata_json['priority'] === 'vip';
    this.lookupWeight = Number(item.metadata_json['weight'] ?? item.sort_order);
    this.editor = 'lookup';
  }
  openNewLookup(): void {
    this.lookupReportGroup = ''; this.lookupReportCode = '';
    this.editingLookup = null; this.lookupVip = false; this.lookupWeight = 10;
    this.newLookup = { category: this.selectedLookupCategory, value: '', label: '', sort_order: 0 }; this.editor = 'lookup';
  }
  saveLookup(): void {
    const label = this.newLookup.label.trim();
    if (!label) return;
    const metadata = { ...(this.editingLookup?.metadata_json || {}) };
    if (this.selectedLookupCategory === 'rank_relationship') metadata['report_group'] = this.lookupReportGroup;
    if (this.reportCodes[this.selectedLookupCategory]) metadata['report_code'] = this.lookupReportCode;
    if (this.selectedLookupCategory === 'rank_relationship') metadata['priority'] = this.lookupVip ? 'vip' : 'normal';
    if (this.selectedLookupCategory === 'priority_category') metadata['weight'] = this.lookupWeight;
    const payload = { ...this.newLookup, category: this.selectedLookupCategory, label,
      value: (this.newLookup.value.trim() || label).toLowerCase().replace(/[^a-z0-9._-]+/g, '_'), metadata_json: metadata };
    const request = this.editingLookup ? this.api.updateLookup(this.editingLookup.id, { label, sort_order: payload.sort_order, metadata_json: metadata }) : this.api.createLookup(payload);
    request.subscribe({ next: item => { this.lookupOptions = [...this.lookupOptions.filter(old => old.id !== item.id), item]; this.editor = ''; this.notify('Dropdown option saved'); }, error: error => this.message = this.apiErrorMessage(error, 'Could not save option.') });
  }
  designationChanged(): void {
    const designation = this.lookupOptions.find(item => item.category === 'rank_relationship' && item.value === this.form.rank);
    if (designation?.metadata_json['priority'] === 'vip' || this.form.rank === 'vip') this.form.priority = 'vip';
  }
  lookupCategoryLabel(category: string): string {
    return ({ rank_relationship: 'Designation / Rank', patient_source: 'Patient source (OPD / Ward)', room_number: 'Room numbers', priority_category: 'Patient priority' } as Record<string,string>)[category] || category.replaceAll('_', ' ');
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
    this.api.action(token.doctor_id || this.selectedDoctorId, token.id, 'complete').subscribe({
      next: () => { this.message = `${token.serial_number || token.token_number} completed.`; this.refresh(); },
      error: () => this.message = 'Unable to complete this consultation.',
    });
  }

  queueAction(token: QueueToken, action: string): void {
    if (['skip', 'no_show', 'cancel'].includes(action)) { this.openAction(token, action); return; }
    this.executeAction(token, action);
  }

  executeAction(token: QueueToken, action: string, reason?: string): void {
    if (this.actionBusy) return;
    this.actionBusy = true;
    this.api.action(this.view === 'doctor' ? this.selectedDoctorId : token.doctor_id || this.selectedDoctorId, token.id, action, reason).subscribe({
      next: () => { this.actionBusy = false; this.actionDialog = null; this.notify(`${token.serial_number || token.token_number} · ${action === 'call_physically' ? 'Called physically' : action.replaceAll('_', ' ')}`); this.refresh(); },
      error: error => { this.actionBusy = false; this.message = this.apiErrorMessage(error, 'Action could not be completed.'); },
    });
  }
  openAction(token: QueueToken, action: string): void {
    this.actionDialog = { token, action }; this.actionReason = ''; this.actionDestination = ''; this.actionPriority = token.priority;
  }
  transferPatient(token: QueueToken): void { this.openAction(token, 'transfer'); }
  togglePriority(token: QueueToken): void { this.openAction(token, 'priority'); }
  submitAction(): void {
    const context = this.actionDialog;
    if (!context || !this.actionReason.trim() || this.actionBusy) return;
    if (!['transfer', 'priority'].includes(context.action)) { this.executeAction(context.token, context.action, this.actionReason.trim()); return; }
    if (context.action === 'transfer' && !this.actionDestination) return;
    this.actionBusy = true;
    const request = context.action === 'transfer'
      ? this.api.transferToken(context.token.id, this.actionDestination, this.actionReason.trim())
      : this.api.updatePriority(context.token.id, this.actionPriority, this.actionReason.trim());
    request.subscribe({ next: () => { this.actionBusy = false; this.actionDialog = null; this.notify('Patient updated'); this.refresh(); },
      error: error => { this.actionBusy = false; this.message = this.apiErrorMessage(error, 'Could not update patient.'); } });
  }

  saveTokenRoom(token: QueueToken): void {
    const roomNumber = (this.tokenRoomDrafts[token.id] ?? token.room_number).trim();
    if (!roomNumber) {
      this.message = 'Room number cannot be empty.';
      return;
    }
    this.api.updateTokenRoom(token.id, roomNumber).subscribe({
      next: (updated) => {
        this.tokenRoomDrafts[updated.id] = updated.room_number;
        this.message = `${updated.serial_number || updated.token_number} room updated to ${updated.room_number}.`;
        this.refresh();
      },
      error: (error) => {
        this.message = error?.error?.detail || 'Room number could not be updated.';
        this.refresh();
      },
    });
  }

  saveSetting(setting: AppSetting): void {
    this.api.saveSetting(setting.key, setting.value).subscribe({ next: () => { this.settings = this.settings.map(item => item.key === setting.key ? structuredClone(setting) : item); this.editor = ''; this.notify(`${setting.key} settings saved.`); }, error: () => this.message = 'Unable to save settings.' });
  }

  testAnnouncement(setting: AppSetting): void {
    this.audioTestBusy = true;
    this.api.testAnnouncement(setting.value).subscribe({
      next: () => {
        this.audioTestBusy = false;
        const label = setting.value['voice_mode'] === 'offline_neural' ? 'Offline neural' : setting.value['voice_mode'] === 'offline' ? 'Basic offline' : 'Automatic';
        this.message = `${label} voice test queued on the server audio output.`;
      },
      error: (error) => {
        this.audioTestBusy = false;
        this.message = error?.error?.detail || 'Unable to test the audio voice.';
      },
    });
  }

  changePassword(): void {
    if (this.passwordForm.next !== this.passwordForm.confirm) {
      this.message = 'New password confirmation does not match.';
      return;
    }
    if (this.passwordForm.next.length < 10) {
      this.message = 'New password must contain at least 10 characters.';
      return;
    }
    this.passwordBusy = true;
    this.api.changePassword(this.passwordForm.current, this.passwordForm.next).subscribe({
      next: () => {
        this.passwordBusy = false;
        this.editor = '';
        this.passwordForm = { current: '', next: '', confirm: '' };
        this.message = 'Password changed. Other signed-in sessions were closed.';
      },
      error: (error) => {
        this.passwordBusy = false;
        this.message = error?.error?.detail || 'Could not change password.';
      },
    });
  }

  loadSettings(): void {
    if (this.hasPermission('settings.manage')) {
      this.api.settings().subscribe((settings) => {
        this.settings = settings.map((setting) => setting.key === 'announcement' ? {
          ...setting,
          value: { voice_mode: 'auto', cache_max_files: 40, ...setting.value },
        } : setting);
      });
    }
    if (this.hasPermission('holidays.view') || this.hasPermission('holidays.manage')) {
      this.api.holidays().subscribe((items) => this.holidays = items);
    }
    if (this.hasPermission('devices.view') || this.hasPermission('devices.manage')) {
      this.api.devices().subscribe((items) => this.devices = items);
    }
    if (this.hasPermission('sms.view')) {
      this.api.smsMessages().subscribe((items) => this.smsMessages = items);
    }
  }

  createHoliday(): void {
    if (!this.newHoliday.holiday_date || !this.newHoliday.name.trim()) return;
    this.api.createHoliday(this.newHoliday).subscribe({
      next: (item) => { this.editor = ''; this.holidays = [...this.holidays, item].sort((a, b) => a.holiday_date.localeCompare(b.holiday_date)); this.newHoliday = { holiday_date: '', name: '' }; },
      error: (error) => this.message = error?.error?.detail || 'Could not add holiday.',
    });
  }

  createDevice(): void {
    if (!this.newDevice.name.trim()) return;
    this.api.createDevice(this.newDevice).subscribe({
      next: (created) => {
        this.editor = '';
        this.devices = [...this.devices, created.device];
        this.message = `Device created. Save this client key now: ${created.client_key}`;
        this.newDevice.name = '';
      },
      error: (error) => this.message = error?.error?.detail || 'Could not create device.',
    });
  }

  loadAppointments(): void {
    if (this.hasPermission('appointments.view')) {
      this.api.appointments().subscribe({
        next: (items) => this.appointments = items,
        error: (error) => this.message = error?.error?.detail || 'Could not load appointments.',
      });
    }
    if (this.hasPermission('patients.view')) this.searchPatients();
    if (this.hasPermission('schedule.view')) {
      this.api.scheduleSlots().subscribe({
        next: (items) => this.allAppointmentSlots = items.filter((item) => new Date(item.ends_at).getTime() > Date.now()),
      });
    }
    if (this.appointmentDoctorId) this.loadAppointmentSlots();
  }

  searchPatients(): void {
    this.api.patients(this.patientSearch.trim()).subscribe({
      next: (items) => this.patients = items,
      error: (error) => this.message = error?.error?.detail || 'Could not search patients.',
    });
  }

  createPatientRecord(): void {
    if (this.newPatient.name.trim().length < 2) {
      this.message = 'Patient name must contain at least 2 characters.';
      return;
    }
    this.api.createPatient({
      name: this.newPatient.name.trim(), mobile: this.newPatient.mobile.trim(),
      title: this.newPatient.title || null, sex: this.newPatient.sex || null,
    }).subscribe({
      next: (patient) => {
        this.patients = [patient, ...this.patients];
        this.appointmentForm.patient_id = patient.id;
        this.newPatient = { name: '', mobile: '', title: '', sex: '' };
        this.message = `${patient.patient_number} registered.`;
      },
      error: (error) => this.message = error?.error?.detail || 'Could not register patient.',
    });
  }

  loadAppointmentSlots(): void {
    this.appointmentForm.slot_id = '';
    if (!this.appointmentDoctorId || !this.hasPermission('schedule.view')) {
      this.appointmentSlots = [];
      return;
    }
    this.api.scheduleSlots(this.appointmentDoctorId).subscribe({
      next: (items) => this.appointmentSlots = items.filter((item) => new Date(item.ends_at).getTime() > Date.now()),
      error: (error) => this.message = error?.error?.detail || 'Could not load appointment slots.',
    });
  }

  createAppointmentRecord(): void {
    if (!this.appointmentForm.patient_id || !this.appointmentDoctorId || !this.appointmentForm.slot_id) {
      this.message = 'Select a patient, doctor and available slot.';
      return;
    }
    this.api.createAppointment({
      patient_id: this.appointmentForm.patient_id,
      doctor_id: this.appointmentDoctorId,
      slot_id: this.appointmentForm.slot_id,
      reason: this.appointmentForm.reason || null,
      notes: this.appointmentForm.notes || null,
    }).subscribe({
      next: (appointment) => {
        this.appointments = [appointment, ...this.appointments];
        this.appointmentForm = { patient_id: '', slot_id: '', reason: '', notes: '' };
        this.message = `${appointment.appointment_number} scheduled.`;
      },
      error: (error) => this.message = error?.error?.detail || 'Could not schedule appointment.',
    });
  }

  appointmentPatient(patientId: string): Patient | undefined { return this.patients.find((item) => item.id === patientId); }
  appointmentDoctor(doctorId: string): Doctor | undefined { return this.doctors.find((item) => item.id === doctorId); }
  appointmentSlot(slotId: string): ScheduleSlot | undefined { return this.appointmentSlots.find((item) => item.id === slotId); }
  slotsForDoctor(doctorId: string): ScheduleSlot[] { return this.allAppointmentSlots.filter((item) => item.doctor_id === doctorId); }

  updateAppointmentRecord(appointment: Appointment, action: 'confirm' | 'cancel'): void {
    const reason = action === 'confirm' ? 'Attendance confirmed by reception' : window.prompt('Cancellation reason:')?.trim();
    if (!reason) return;
    this.api.updateAppointment(appointment.id, action, reason).subscribe({
      next: (updated) => this.appointments = this.appointments.map((item) => item.id === updated.id ? updated : item),
      error: (error) => this.message = error?.error?.detail || `Could not ${action} appointment.`,
    });
  }

  rescheduleAppointment(appointment: Appointment): void {
    const slotId = this.rescheduleSlots[appointment.id];
    if (!slotId) {
      this.message = 'Select a replacement slot first.';
      return;
    }
    this.api.updateAppointment(appointment.id, 'reschedule', 'Rescheduled by reception', slotId).subscribe({
      next: (updated) => {
        this.appointments = this.appointments.map((item) => item.id === updated.id ? updated : item);
        delete this.rescheduleSlots[appointment.id];
        this.message = `${updated.appointment_number} rescheduled.`;
      },
      error: (error) => this.message = error?.error?.detail || 'Could not reschedule appointment.',
    });
  }

  checkInAppointment(appointment: Appointment): void {
    this.api.checkInAppointment(appointment.id).subscribe({
      next: (token) => {
        appointment.status = 'checked_in';
        this.message = `${token.serial_number || token.token_number} created and added to the live queue.`;
        this.printSlip(token);
      },
      error: (error) => this.message = error?.error?.detail || 'Could not check in appointment.',
    });
  }

  reportEntries(group?: Record<string, number>): [string, number][] { return Object.entries(group || {}).sort((a, b) => b[1] - a[1]); }

  canAction(token: QueueToken, action: string): boolean {
    if (!this.hasPermission('queue.action')) return false;
    const states: Record<string, string[]> = { start: ['called', 'recalled'], complete: ['in_progress'], skip: ['called', 'recalled'], recall: ['skipped', 'called', 'recalled'], no_show: ['called', 'recalled', 'skipped'], cancel: ['waiting', 'called', 'recalled', 'skipped', 'in_progress'] };
    if (action === 'call_physically') return token.priority === 'vip' && token.status === 'waiting';
    return states[action]?.includes(token.status) || false;
  }

  refresh(showIndicator = true): void {
    if (showIndicator) this.isRefreshing = true;
    if (this.view === 'dashboard') { this.loadDashboard(); if (this.dashboardDetail) this.loadDashboardPatients(false); return; }
    if (this.view === 'display') {
      if (!this.selectedWaitingRoom) { this.isRefreshing = false; return; }
      this.api.display(this.selectedWaitingRoom).subscribe({
        next: (state) => { this.displayState = state; this.speakDisplay(state); this.markSynced(); },
        error: () => this.markOffline(),
      });
      return;
    }
    if (this.view !== 'reception' && this.view !== 'doctor') { this.isRefreshing = false; return; }
    if (this.view === 'doctor' && !this.doctorOpened) { this.isRefreshing = false; return; }
    if (!this.selectedDoctorId && this.view !== 'reception') {
      this.tokens = [];
      this.isRefreshing = false;
      return;
    }
    const requestView = this.view;
    const requestDoctor = this.view === 'reception' ? '' : this.selectedDoctorId;
    this.api.listTokens(requestDoctor, requestView === 'doctor').subscribe({
      next: (tokens) => {
        if (this.view !== requestView || (requestView === 'doctor' && this.selectedDoctorId !== requestDoctor)) return;
        this.tokens = tokens;
        for (const token of tokens) {
          if (this.tokenRoomDrafts[token.id] === undefined || token.status !== 'waiting') {
            this.tokenRoomDrafts[token.id] = token.room_number;
          }
        }
        this.markSynced();
      },
      error: () => this.markOffline(),
    });
  }

  openSetting(setting: AppSetting): void { this.editingSetting = structuredClone(setting); this.editor = 'setting'; }
  openRole(role: RoleDefinition): void { this.roleDraft = structuredClone(role); this.editor = 'role'; }
  openUser(user: AuthUser): void { this.editingUser = structuredClone(user); this.editor = 'user'; }
  saveUserAssignment(): void {
    const user = this.editingUser; if (!user) return;
    this.api.updateUser(user.id, { role: user.role, doctor_id: this.roleProfile(user.role) === 'radiographer' ? user.doctor_id || null : null }).subscribe({ next: updated => { this.users = this.users.map(item => item.id === updated.id ? updated : item); this.editor = ''; this.notify('Assignment saved'); }, error: error => this.message = this.apiErrorMessage(error, 'Could not save assignment.') });
  }

  notify(message: string): void {
    this.message = message; clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => { if (this.message === message) this.message = ''; }, 6500);
  }
  openDoctor(doctor: Doctor): void { this.selectedDoctorId = doctor.id; this.doctorOpened = true; this.tokens = []; this.refresh(); }
  openDashboardDetail(detail: string): void {
    this.dashboardDetail = detail;
    const url = new URL(window.location.href); url.searchParams.set('detail', detail); window.history.pushState({}, '', url);
    this.loadDashboardPatients(); window.scrollTo({ top: 0 });
  }
  get dashboardDetailTitle(): string { return ({ all: 'All patients today', waiting: 'Waiting patients', called: 'Called patients', in_progress: 'Patients in service', completed: 'Completed patients', vip: 'VIP patients', wait: 'Patient waiting times' } as Record<string,string>)[this.dashboardDetail] || 'Patients'; }
  loadDashboardPatients(showLoading = true): void {
    if (showLoading) { this.detailLoading = true; this.dashboardPatients = []; }
    this.detailError = '';
    const detail = this.dashboardDetail;
    this.api.dashboardPatients(detail).subscribe({next: rows => { if (detail === this.dashboardDetail) { this.dashboardPatients = rows; this.detailLoading = false; } }, error: error => { if (detail === this.dashboardDetail) { this.detailLoading = false; this.detailError = this.apiErrorMessage(error, 'Could not load patient details.'); } }});
  }
  @HostListener('window:popstate') restorePage(): void {
    const params = new URLSearchParams(location.search); const view = (params.get('view') || 'dashboard') as View;
    if (this.canView(view)) { this.view = view; this.dashboardDetail = params.get('detail') || ''; this.doctorOpened = false; this.refresh(); }
  }
  leaveDisplay(): void { this.setView(this.canView(this.previousView) ? this.previousView : 'settings'); }
  openClaim(): void {
    this.editor = 'claim'; this.claimLoading = true; this.claimCandidates = [];
    this.api.availablePatients(this.selectedDoctorId).subscribe({ next: rows => { this.claimCandidates = rows; this.claimLoading = false; }, error: error => { this.claimLoading = false; this.message = this.apiErrorMessage(error, 'Could not load available patients.'); } });
  }
  claimPatient(token: QueueToken): void {
    if (this.actionBusy) return; this.actionBusy = true;
    this.api.claimPatient(this.selectedDoctorId, token.id).subscribe({ next: updated => { this.actionBusy = false; this.editor = ''; this.notify(`Patient assigned to room ${updated.room_number}`); this.refresh(); }, error: error => { this.actionBusy = false; this.message = this.apiErrorMessage(error, 'Patient is no longer available.'); this.refresh(); } });
  }
  exportTodayReport(): void {
    this.reportFilters = { date_from: this.registrationDate, date_to: this.registrationDate, doctor_id: '', waiting_room: '', status: '', priority: '', service_category: '' };
    this.loadReceptionReport(); this.exportReceptionReport();
  }

  dismissMessage(): void { this.message = ''; }

  private markSynced(): void {
    this.dataStatus = 'online';
    this.lastSyncedAt = new Date();
    this.isRefreshing = false;
  }

  private markOffline(): void {
    this.dataStatus = 'offline';
    this.isRefreshing = false;
  }

  private afterCall(token: QueueToken): void {
    const identity = token.service_number ? `${token.service_number} — ${token.patient_name}` : token.patient_name;
    this.message = `${identity} called to room ${token.room_number}.`;
    this.busy = false;
    this.refresh();
  }

  private connectRealtime(): void {
    if (!this.selectedWaitingRoom) return;
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
    return this.lookupOptions.find((item) => item.category === 'service_category' && item.value === category)?.label || category;
  }

  private speakDisplay(state: DisplayState): void {
    // Audio is played centrally by the backend PC connected to the hospital PA.
    // The display only tracks the latest event; no browser/device sound is used.
    if (state.current) this.lastSpokenTokenId = state.current.id;
  }
}
