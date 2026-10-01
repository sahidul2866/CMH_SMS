import '@angular/compiler';
import { ElementRef, Injector, runInInjectionContext } from '@angular/core';
import { build } from 'esbuild';
import { BehaviorSubject, Subject, defer, of } from 'rxjs';
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

// Bundle local TS components without rendering a browser UI. Angular/RxJS remain
// real dependencies; only HTTP, sockets and the browser environment are faked.
const root = fileURLToPath(new URL('../', import.meta.url));
const temporary = await mkdtemp(path.join(root, 'node_modules/.live-refresh-test-'));
after(() => rm(temporary, { recursive: true, force: true }));
const output = path.join(temporary, 'component.mjs');
await build({
  stdin: { contents: `export {SearchableSelectComponent} from './src/app/searchable-select.component'; export {ClientLogService} from './src/app/client-log.service'; export {AppComponent} from './src/app/app.component'; export {QueueApiService} from './src/app/queue-api.service'; export {RealtimeService} from './src/app/realtime.service';`, resolveDir: root },
  tsconfig: path.join(root, 'tsconfig.json'), bundle: true, packages: 'external', platform: 'node', format: 'esm', outfile: output,
});
const { SearchableSelectComponent, ClientLogService, AppComponent, QueueApiService, RealtimeService } = await import(pathToFileURL(output));

function fixture(t) {
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'], now: Date.now() });
  const location = { search: '?view=reception', href: 'http://localhost/?view=reception' };
  globalThis.document = { hidden: false, documentElement: { dataset: {} } };
  globalThis.window = { location, history: {pushState() {}}, scrollTo() {} };
  globalThis.location = location;
  Object.defineProperty(globalThis, 'navigator', {value: {onLine: true}, configurable: true});
  const user = {id: 'staff', username: 'staff', role: 'reception', permissions: ['pages.reception', 'queue.view', 'directory.view', 'master_data.view', 'pages.dashboard', 'dashboard.view', 'pages.radiographer', 'pages.display', 'display.view']};
  const responses = {
    session: user,
    listDoctors: [{id: 'doctor', name: 'Doctor', room: '205', waitingRoom: 'WR-1'}],
    listWaitingRooms: [{id: 'room', code: 'WR-1'}],
    listTokens: [], lookups: [], radiographerStatus: [], dashboard: {total: 0}, dashboardPatients: [],
    display: {current: null, active_calls: [], next_tokens: []},
    registrationFields: {fields: {patient_name: 'Name'}, required: ['patient_name'], enabled: ['patient_name'], custom: []},
  };
  const counts = {};
  const api = new Proxy({}, {get: (_, key) => () => defer(() => {
    counts[key] = (counts[key] || 0) + 1;
    assert.ok(key in responses, `Unexpected API call: ${String(key)}`);
    const response = responses[key];
    return response instanceof Subject ? response : of(response);
  })});
  const events = new Subject();
  const status = new BehaviorSubject('connected');
  const realtime = {status$: status, connect: () => events};
  const injector = Injector.create({providers: [{provide: ClientLogService, useValue: {navigation() {}, record() {}}}, {provide: QueueApiService, useValue: api}, {provide: RealtimeService, useValue: realtime}]});
  const app = runInInjectionContext(injector, () => new AppComponent());
  t.after(() => { app.ngOnDestroy(); injector.destroy(); });
  events.next({type: 'connection.ready'});
  t.mock.timers.tick(150);
  return {app, events, status, counts, responses};
}

test('connected idle screen and heartbeat events issue no periodic HTTP requests', t => {
  const {counts, events} = fixture(t);
  assert.equal(counts.listTokens, 1);
  const before = {...counts};
  for (let i = 0; i < 8; i++) { events.next({type: 'heartbeat'}); t.mock.timers.tick(15000); }
  assert.deepEqual(counts, before);
});

test('event bursts refresh once; hidden tabs catch up once on return', t => {
  const {app, counts, events} = fixture(t);
  for (let i = 0; i < 20; i++) events.next({type: 'data.changed', topics: ['queue']});
  t.mock.timers.tick(150);
  assert.equal(counts.listTokens, 2);
  document.hidden = true;
  app.onVisibilityChange();
  events.next({type: 'data.changed', topics: ['queue']});
  t.mock.timers.tick(60000);
  assert.equal(counts.listTokens, 2);
  document.hidden = false;
  app.onVisibilityChange();
  t.mock.timers.tick(150);
  assert.equal(counts.listTokens, 3);
});

test('disconnected live screens use 30-second recovery; settings do not poll', t => {
  const {app, counts, status} = fixture(t);
  status.next('offline');
  t.mock.timers.tick(29000);
  assert.equal(counts.listTokens, 1);
  t.mock.timers.tick(1000);
  t.mock.timers.tick(150);
  assert.equal(counts.listTokens, 2);
  app.setView('settings');
  const before = {...counts};
  t.mock.timers.tick(120000);
  assert.deepEqual(counts, before);
});

test('navigation cancels old requests and stale results cannot replace a new view', t => {
  const {app, counts, responses, events} = fixture(t);
  const slow = new Subject();
  responses.listTokens = slow;
  events.next({type: 'data.changed', topics: ['queue']});
  t.mock.timers.tick(150);
  assert.equal(slow.observed, true);
  app.setView('dashboard');
  assert.equal(slow.observed, false);
  slow.next([{id: 'stale-patient'}]); slow.complete();
  t.mock.timers.tick(150);
  assert.equal(counts.dashboard, 1);
  assert.deepEqual(app.tokens, []);
});

test('reconnection refreshes permissions and current data without restarting polling', t => {
  const {counts, status, events} = fixture(t);
  status.next('recovering');
  status.next('connected');
  events.next({type: 'connection.ready'});
  t.mock.timers.tick(150);
  t.mock.timers.tick(150);
  assert.equal(counts.session, 2);
  assert.equal(counts.listTokens, 2);
  const before = {...counts};
  t.mock.timers.tick(120000);
  assert.deepEqual(counts, before);
});

test('browser diagnostics batch and deduplicate errors without retrying a failed upload', async t => {
  const {HttpBackend, HttpResponse} = await import('@angular/common/http');
  t.mock.timers.enable({apis: ['setTimeout', 'Date'], now: Date.now()});
  globalThis.document = {documentElement: {dataset: {}}};
  const requests = [];
  const responses = [];
  const injector = Injector.create({providers: [{provide: HttpBackend, useValue: {handle(request) {
    requests.push(request); const response = new Subject(); responses.push(response); return response;
  }}}]});
  const logs = runInInjectionContext(injector, () => new ClientLogService());
  const error = new Error('Private patient name and password');
  logs.error(error); logs.error(error);
  t.mock.timers.tick(1000);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].body.events.length, 1);
  assert.ok(!JSON.stringify(requests[0].body).includes('Private patient'));
  responses[0].error(new Error('Server unavailable'));
  t.mock.timers.tick(120000);
  assert.equal(requests.length, 1, 'failed diagnostics never start a retry timer');
  logs.record({event: 'network_state', state: 'online'});
  t.mock.timers.tick(1000);
  assert.equal(requests.length, 2);
  responses[1].next(new HttpResponse({status: 204})); responses[1].complete();
  t.mock.timers.tick(120000);
  assert.equal(requests.length, 2, 'idle diagnostics never poll');
  injector.destroy();
});

test('service search debounces, cancels stale responses and fills the selected family member', t => {
  const {app, counts, responses} = fixture(t);
  const old = new Subject();
  responses.serviceNumberSuggestions = old;
  app.form.service_number = 'BA'; app.serviceNumberChanged();
  t.mock.timers.tick(100);
  app.form.service_number = 'BA-1'; app.serviceNumberChanged();
  t.mock.timers.tick(299);
  assert.equal(counts.serviceNumberSuggestions, undefined);
  t.mock.timers.tick(1);
  assert.equal(counts.serviceNumberSuggestions, 1);
  const current = new Subject();
  responses.serviceNumberSuggestions = current;
  app.form.service_number = 'BA-12'; app.serviceNumberChanged();
  t.mock.timers.tick(300);
  old.next({items: [{patient_name: 'Wrong person'}], has_more: false});
  assert.deepEqual(app.serviceSuggestions, []);
  const child = {id: 'child', service_number: 'BA-12', patient_name: 'Child Name', patient_phone: '123', unit: 'Unit 4',
    beneficiary_type: 'family', entitlement: 'military', family_relationship: 'child', rank: 'major', service_category: 'dependant', age: 12};
  current.next({items: [child], has_more: false}); current.complete();
  app.form.priority = 'normal'; app.form.mri_area = 'Knee';
  app.selectServiceSuggestion(child);
  assert.equal(app.form.patient_name, 'Child Name');
  assert.equal(app.form.rank, 'major');
  assert.equal(app.form.priority, 'normal');
  assert.equal(app.form.mri_area, 'Knee');
  assert.equal(app.form.age, 12);
  assert.equal(app.serviceSearchOpen, false);
});

test('rank stays in the single registration control when switching to family and back', t => {
  const {app} = fixture(t);
  app.form.rank = 'major';
  app.form.beneficiary_type = 'family'; app.classificationChanged(app.form);
  assert.equal(app.form.rank, 'major');
  app.form.rank = 'captain';
  app.form.beneficiary_type = 'self'; app.classificationChanged(app.form);
  assert.equal(app.form.rank, 'captain');
  assert.equal('sponsor_rank' in app.form, false);
  app.form.patient_source = 'ipd';
  assert.equal(app.isWardSource, true);
  app.form.ward_text = 'Ward 7'; app.form.patient_source = 'opd'; app.patientSourceChanged();
  assert.equal(app.form.ward_text, '');
});

test('patient type merges entitlement choices (Self, Family, RE, CNE) with appropriate field applicability', t => {
  const {app} = fixture(t);
  assert.equal(app.fieldApplicable('entitlement'), false);

  // Self
  app.form.beneficiary_type = 'self';
  app.classificationChanged(app.form);
  assert.equal(app.form.entitlement, 'military');
  assert.equal(app.fieldApplicable('service_status'), true);
  assert.equal(app.fieldApplicable('family_relationship'), false);

  // Family
  app.form.beneficiary_type = 'family';
  app.form.family_relationship = 'spouse';
  app.form.service_status = 'serving';
  app.classificationChanged(app.form);
  assert.equal(app.form.entitlement, 'military');
  assert.equal(app.fieldApplicable('service_status'), true);
  assert.equal(app.fieldApplicable('family_relationship'), true);

  // RE
  app.form.beneficiary_type = 're';
  app.classificationChanged(app.form);
  assert.equal(app.form.entitlement, 're');
  assert.equal(app.form.service_status, '');
  assert.equal(app.form.family_relationship, '');
  assert.equal(app.fieldApplicable('service_status'), false);
  assert.equal(app.fieldApplicable('family_relationship'), false);

  // CNE
  app.form.beneficiary_type = 'cne';
  app.classificationChanged(app.form);
  assert.equal(app.form.entitlement, 'cne');
  assert.equal(app.form.service_status, '');
  assert.equal(app.form.family_relationship, '');
  assert.equal(app.fieldApplicable('service_status'), false);
  assert.equal(app.fieldApplicable('family_relationship'), false);

  // enabledPayload includes entitlement even if not a standard registration input
  const payload = app.enabledPayload(app.form);
  assert.equal(payload.beneficiary_type, 'cne');
  assert.equal(payload.entitlement, 'cne');
});

test('reception report filters support date range, contrast used, family, re, and cne', t => {
  const {app} = fixture(t);

  // Quick filter for contrast used
  app.setReportQuickFilter('', 'used');
  assert.equal(app.reportFilters.contrast, 'used');
  assert.equal(app.hasActiveReportFilters, true);
  let params = app.receptionReportParams();
  assert.equal(params.contrast, 'used');
  assert.equal('beneficiary_type' in params, false);

  // Quick filter for family
  app.setReportQuickFilter('family', 'used');
  assert.equal(app.reportFilters.beneficiary_type, 'family');
  params = app.receptionReportParams();
  assert.equal(params.beneficiary_type, 'family');
  assert.equal(params.contrast, 'used');

  // Quick filter for re
  app.setReportQuickFilter('re', '');
  assert.equal(app.reportFilters.beneficiary_type, 're');
  assert.equal(app.reportFilters.contrast, '');
  params = app.receptionReportParams();
  assert.equal(params.beneficiary_type, 're');
  assert.equal('contrast' in params, false);

  // Quick filter for cne
  app.setReportQuickFilter('cne', '');
  assert.equal(app.reportFilters.beneficiary_type, 'cne');
  params = app.receptionReportParams();
  assert.equal(params.beneficiary_type, 'cne');

  // Reset filters
  app.resetReportFilters();
  assert.equal(app.reportFilters.beneficiary_type, '');
  assert.equal(app.reportFilters.contrast, '');
  assert.equal(app.hasActiveReportFilters, false);
});



test('rank accepts custom text, retains it on blur, and reuses matching suggestions', () => {
  const injector = Injector.create({providers: [{provide: ElementRef, useValue: {nativeElement: {}}}]});
  const control = runInInjectionContext(injector, () => new SearchableSelectComponent());
  control.allowCustom = true;
  control.searchOnly = true;
  control.options = [{value: 'captain', label: 'Captain'}];
  let saved = '';
  control.registerOnChange(value => saved = value);
  control.search('Research Specialist');
  assert.equal(saved, 'Research Specialist');
  control.close();
  assert.equal(control.text, 'Research Specialist');
  control.options = [{value: 'captain', label: 'Captain'}, {value: 'research_specialist', label: 'Research Specialist'}];
  control.search('research specialist');
  assert.equal(saved, 'research_specialist');
  control.close();
  assert.equal(control.text, 'Research Specialist');
  control.search('');
  assert.equal(saved, '');
});
