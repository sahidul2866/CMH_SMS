export type View = 'dashboard' | 'reception' | 'appointments' | 'doctor' | 'reports' | 'reception-report' | 'settings' | 'display';

export interface AuthUser {
  id: string;
  username: string;
  full_name: string;
  role: string;
  access_profile?: 'admin' | 'reception' | 'radiographer' | 'auditor' | 'display';
  permissions: string[];
  doctor_id?: string | null;
  is_active: boolean;
}

export interface RoleDefinition {
  name: string;
  display_name: string;
  access_profile: 'admin' | 'reception' | 'radiographer' | 'auditor' | 'display';
  description: string;
  permissions: string[];
  is_system: boolean;
}

export interface PermissionDefinition {
  key: string;
  label: string;
  group: string;
}

export interface Doctor {
  id: string;
  name: string;
  department: string;
  room: string;
  waitingRoom: string;
}

export interface PatientClassification {
  beneficiary_type?: string | null;
  service_status?: string | null;
  entitlement?: string | null;
  sponsor_rank?: string | null;
  family_relationship?: string | null;
  rank?: string | null;
}

export interface MonthlySummary {
  month: string; basis: string;
  columns: {key: string; group: string; label: string}[];
  rows: {date: string; counts: Record<string, number>; total: number}[];
  totals: Record<string, number>; total: number;
}

export interface QueueToken extends PatientClassification {
  summary_category?: string | null;
  id: string;
  token_number: string;
  serial_number?: string | null;
  age?: number | null;
  unit?: string | null;
  mri_area?: string | null;
  contrast?: number | null;
  film?: number | null;
  report?: string | null;
  patient_source?: string | null;
  patient_title?: string | null;
  patient_name: string;
  patient_phone: string;
  service_category: string;
  rank?: string | null;
  service_number?: string | null;
  doctor_id: string | null;
  doctor_name: string;
  department: string;
  room_number: string;
  waiting_room: string;
  source: string;
  priority: string;
  status: string;
  waiting_minutes: number;
  created_at: string;
  scheduled_at?: string | null;
  recall_count: number;
}

export interface ReceptionReportRow extends QueueToken {
  token_date: string;
  called_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface QueueReport { total: number; by_status: Record<string, number>; by_doctor: Record<string, number>; by_room: Record<string, number>; by_source: Record<string, number>; priority: number; }
export interface RadiographerDashboardRow {
  doctor_id: string; doctor_name: string; department: string; room_number: string; waiting_room: string;
  waiting: number; called: number; in_progress: number; completed: number; total: number; average_wait_minutes: number; vip: number;
}
export interface RadiographyDashboard {
  scope: 'assigned' | 'all'; generated_at: string; total: number; waiting: number; called: number;
  in_progress: number; completed: number; average_wait_minutes: number;
  vip_total: number; vip_waiting: number; vip_active: number; vip_completed: number;
  radiographers: RadiographerDashboardRow[];
}
export interface AuditEvent { id: string; action: string; actor: string; token_id?: string | null; previous_status?: string | null; new_status?: string | null; reason?: string | null; detail: Record<string, unknown>; created_at: string; }
export interface AppSetting { key: string; value: Record<string, any>; description: string; updated_at: string; }
export interface LookupOption {
  id: string;
  category: string;
  value: string;
  label: string;
  sort_order: number;
  metadata_json: Record<string, unknown>;
  is_active: boolean;
}
export interface Holiday { id: string; holiday_date: string; name: string; is_active: boolean; }
export interface DeviceEndpoint {
  id: string; name: string; device_type: 'display' | 'audio'; waiting_room: string;
  is_active: boolean; last_heartbeat_at?: string | null; fault?: string | null;
}
export interface SmsMessage {
  id: string; mobile: string; message_type: string; body: string; status: string;
  attempts: number; error?: string | null; created_at: string;
}
export interface Patient {
  id: string; patient_number: string; title?: string | null; name: string; mobile: string;
  date_of_birth?: string | null; sex?: string | null; created_at: string;
}
export interface ScheduleSlot {
  id: string; doctor_id: string; starts_at: string; ends_at: string; capacity: number; is_active: boolean;
}
export interface Appointment {
  id: string; appointment_number: string; patient_id: string; doctor_id: string; slot_id: string;
  status: string; reason?: string | null; notes?: string | null; created_by: string;
  created_at: string; checked_in_at?: string | null;
}

export interface DisplayState {
  waiting_room: string;
  current: QueueToken | null;
  active_calls: QueueToken[];
  next_tokens: QueueToken[];
  announcement: string | null;
}

export interface WaitingRoom {
  id: string;
  code: string;
  name: string;
  floor: string;
  display_label: string;
}

export type RealtimeStatus = 'connecting' | 'connected' | 'recovering' | 'offline';

export interface RealtimeEvent {
  event_id: string;
  sequence: number;
  type: 'connection.ready' | 'heartbeat' | 'queue.updated' | 'patient.called';
  reason: string;
  waiting_room: string;
  occurred_at: string;
  display?: DisplayState;
}
