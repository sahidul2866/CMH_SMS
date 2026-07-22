export type View = 'reception' | 'doctor' | 'reports' | 'settings' | 'display';

export interface Doctor {
  id: string;
  name: string;
  department: string;
  room: string;
  waitingRoom: string;
}

export interface QueueToken {
  id: string;
  token_number: string;
  patient_name: string;
  patient_phone: string;
  service_category: string;
  rank?: string | null;
  service_number?: string | null;
  doctor_id: string;
  doctor_name: string;
  department: string;
  room_number: string;
  waiting_room: string;
  source: string;
  priority: string;
  status: string;
  waiting_minutes: number;
  created_at: string;
  recall_count: number;
}

export interface QueueReport { total: number; by_status: Record<string, number>; by_doctor: Record<string, number>; by_room: Record<string, number>; by_source: Record<string, number>; priority: number; }
export interface AuditEvent { id: string; action: string; actor: string; token_id?: string | null; previous_status?: string | null; new_status?: string | null; reason?: string | null; detail: Record<string, unknown>; created_at: string; }
export interface AppSetting { key: string; value: Record<string, any>; description: string; updated_at: string; }

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
