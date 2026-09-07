import { HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { of } from 'rxjs';

import { Doctor, QueueToken, WaitingRoom } from './models';

const doctors: Doctor[] = [
  { id: 'dr-khan', name: 'Dr. Ayesha Khan', department: 'Radiology', room: '205', waitingRoom: 'WR-1' },
  { id: 'dr-rahman', name: 'Dr. Farhan Rahman', department: 'Radiology', room: '207', waitingRoom: 'WR-1' },
];
const rooms: WaitingRoom[] = [
  { id: 'waiting-room-1', code: 'WR-1', name: 'Radiology Waiting Room', floor: '2nd Floor', display_label: 'Radiology' },
];
const now = new Date().toISOString();
let tokens: QueueToken[] = [
  { id: 'demo-1', token_number: 'RD-001', patient_name: 'Md. Rahim Uddin', patient_phone: '01700000001', service_category: 'army', rank: 'Major', service_number: 'BA-10234', doctor_id: 'dr-khan', doctor_name: 'Dr. Ayesha Khan', department: 'Radiology', room_number: '205', waiting_room: 'WR-1', source: 'walk_in', priority: 'normal', status: 'waiting', waiting_minutes: 12, created_at: now, recall_count: 0 },
  { id: 'demo-2', token_number: 'RD-002', patient_name: 'Nusrat Jahan', patient_phone: '01800000002', service_category: 'dependant', doctor_id: 'dr-khan', doctor_name: 'Dr. Ayesha Khan', department: 'Radiology', room_number: '205', waiting_room: 'WR-1', source: 'walk_in', priority: 'vip', status: 'waiting', waiting_minutes: 7, created_at: now, recall_count: 0 },
  { id: 'demo-3', token_number: 'RD-003', patient_name: 'Abdul Karim', patient_phone: '01900000003', service_category: 'retired', doctor_id: 'dr-rahman', doctor_name: 'Dr. Farhan Rahman', department: 'Radiology', room_number: '207', waiting_room: 'WR-1', source: 'appointment', priority: 'normal', status: 'called', waiting_minutes: 5, created_at: now, recall_count: 0 },
];

const json = (body: unknown, status = 200) => of(new HttpResponse({ body, status }));
let lookupValues = [
  ['service_category', 'army', 'Bangladesh Army'], ['service_category', 'dependant', 'Service dependant'], ['service_category', 'retired', 'Retired service'], ['service_category', 'civilian', 'Civilian'],
  ['priority_category', 'normal', 'Normal'], ['priority_category', 'priority', 'Priority'], ['priority_category', 'urgent', 'Urgent'], ['priority_category', 'vip', 'VIP'],
  ['patient_source', 'opd', 'OPD'], ['patient_source', 'ipd', 'IPD / Ward'], ['patient_source', 'emergency', 'Emergency'], ['rank_relationship', 'brigadier_general', 'Brigadier General'], ['rank_relationship', 'shoinik', 'Shoinik / Sainik'], ['rank_relationship', 'vip', 'VIP'], ['room_number', '205', 'Room 205'], ['room_number', '207', 'Room 207'], ['rank_relationship', 'officer', 'Officer'], ['rank_relationship', 'soldier', 'Soldier'],
].map(([category, value, label], index) => ({ id: `lookup-${index}`, category, value, label, sort_order: index, metadata_json: (value === 'brigadier_general' || value === 'vip' ? { priority: 'vip' } : {}) as Record<string, unknown>, is_active: true }));

function dashboard() {
  const rows = doctors.map((doctor) => {
    const items = tokens.filter((token) => token.doctor_id === doctor.id);
    return { doctor_id: doctor.id, doctor_name: doctor.name, department: doctor.department, room_number: doctor.room, waiting_room: doctor.waitingRoom, total: items.length, waiting: items.filter((item) => item.status === 'waiting').length, called: items.filter((item) => ['called', 'recalled'].includes(item.status)).length, in_progress: items.filter((item) => item.status === 'in_progress').length, completed: items.filter((item) => item.status === 'completed').length, average_wait_minutes: 6, vip: items.filter((item) => item.priority === 'vip').length };
  });
  const vip = tokens.filter((item) => item.priority === 'vip');
  return { scope: 'all', generated_at: new Date().toISOString(), total: tokens.length, waiting: tokens.filter((item) => item.status === 'waiting').length, called: tokens.filter((item) => ['called', 'recalled'].includes(item.status)).length, in_progress: tokens.filter((item) => item.status === 'in_progress').length, completed: tokens.filter((item) => item.status === 'completed').length, average_wait_minutes: 6, vip_total: vip.length, vip_waiting: vip.filter((item) => item.status === 'waiting').length, vip_active: vip.filter((item) => ['called', 'recalled', 'in_progress'].includes(item.status)).length, vip_completed: vip.filter((item) => item.status === 'completed').length, radiographers: rows };
}

export const demoInterceptor: HttpInterceptorFn = (request, next) => {
  if (document.documentElement.dataset['demo'] !== 'true' || !request.url.startsWith('/api/v1/')) return next(request);
  const path = request.url.slice('/api/v1'.length);
  if (path === '/doctors' && request.method === 'GET') return json(doctors);
  if (path === '/waiting-rooms' && request.method === 'GET') return json(rooms);
  if (path === '/lookups' && request.method === 'GET') return json(lookupValues);
  if (path === '/registration-preview') return json({ serial_number: `${String(tokens.length + 1).padStart(5, '0')}/${String(new Date().getFullYear()).slice(-2)}`, date: new Intl.DateTimeFormat('en-CA').format(new Date()) });
  if (path === '/dashboard/patients') {
    const status = request.params.get('status') || 'all';
    return json(tokens.filter(token => ['all', 'wait'].includes(status) || (status === 'vip' ? token.priority === 'vip' : status === 'called' ? ['called', 'recalled'].includes(token.status) : token.status === status)));
  }
  if (path === '/lookups' && request.method === 'POST') {
    const item = { ...(request.body as typeof lookupValues[number]), id: `lookup-${Date.now()}`, is_active: true };
    lookupValues = [...lookupValues, item]; return json(item, 201);
  }
  const lookupMatch = path.match(/^\/lookups\/([^/]+)$/);
  if (lookupMatch && request.method === 'PATCH') {
    const item = lookupValues.find(item => item.id === lookupMatch[1])!;
    Object.assign(item, request.body); return json(item);
  }
  if (path === '/dashboard' && request.method === 'GET') return json(dashboard());
  if (path === '/tokens' && request.method === 'GET') {
    const doctorId = request.params.get('doctor_id');
    return json(doctorId ? tokens.filter((token) => token.doctor_id === doctorId || (request.params.get('shared_waiting') === 'true' && token.status === 'waiting')) : tokens);
  }
  if (path === '/tokens' && request.method === 'POST') {
    const body = request.body as Record<string, string>;
    if (['vip', 'brigadier_general'].includes(body['rank'])) body['priority'] = 'vip';
    const token: QueueToken = { ...(body as unknown as QueueToken), id: `demo-${Date.now()}`, doctor_id: null, doctor_name: '', department: '', room_number: '', waiting_room: '', token_number: `RD-${String(tokens.length + 1).padStart(3, '0')}`, serial_number: `${String(tokens.length + 1).padStart(5, '0')}/${String(new Date().getFullYear()).slice(-2)}`, status: 'waiting', waiting_minutes: 0, created_at: new Date().toISOString(), recall_count: 0 };
    tokens = [...tokens, token];
    return json(token, 201);
  }
  const roomMatch = path.match(/^\/tokens\/([^/]+)\/room$/);
  if (roomMatch && request.method === 'PATCH') {
    const token = tokens.find((item) => item.id === roomMatch[1])!;
    token.room_number = (request.body as { room_number: string }).room_number;
    return json(token);
  }
  const callNextMatch = path.match(/^\/doctors\/([^/]+)\/call-next$/);
  const callMatch = path.match(/^\/doctors\/([^/]+)\/tokens\/([^/]+)\/call$/);
  if ((callNextMatch || callMatch) && request.method === 'POST') {
    const doctorId = (callNextMatch || callMatch)![1];
    const tokenId = callMatch?.[2];
    const token = tokens.find((item) => item.status === 'waiting' && item.priority !== 'vip' && (!tokenId || item.id === tokenId))!;
    const doctor = doctors.find(item => item.id === doctorId)!;
    token.doctor_id = doctor.id; token.doctor_name = doctor.name; token.room_number = doctor.room; token.waiting_room = doctor.waitingRoom;
    token.status = 'called';
    return json(token);
  }
  const actionMatch = path.match(/^\/doctors\/([^/]+)\/tokens\/([^/]+)\/action$/);
  if (actionMatch && request.method === 'POST') {
    const token = tokens.find((item) => item.id === actionMatch[2])!;
    const action = (request.body as { action: string }).action;
    if (action === 'call_physically') { const doctor = doctors.find(item => item.id === actionMatch[1])!; token.doctor_id = doctor.id; token.doctor_name = doctor.name; token.room_number = doctor.room; token.waiting_room = doctor.waitingRoom; }
    token.status = ({ call_physically: 'in_progress', cancel: 'cancelled', start: 'in_progress', complete: 'completed', skip: 'skipped', recall: 'recalled', no_show: 'no_show' } as Record<string, string>)[action] || token.status;
    return json(token);
  }
  if (path.startsWith('/displays/') && request.method === 'GET') {
    const active = tokens.filter((item) => ['called', 'recalled'].includes(item.status));
    return json({ waiting_room: 'WR-1', current: active[0] || null, active_calls: active, next_tokens: tokens.filter((item) => item.status === 'waiting').slice(0, 5), announcement: null });
  }
  if (path === '/reports/reception') return json(tokens.map(token => ({ ...token, token_date: new Intl.DateTimeFormat('en-CA').format(new Date()) })));
  if (path === '/reports/queue-summary') return json({ total: tokens.length, by_status: {}, by_doctor: {}, by_room: { 'WR-1': tokens.length }, by_source: {}, priority: 1 });
  if (path === '/audit') return json([]);
  return json([]);
};
