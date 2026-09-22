import '@angular/compiler';
import { Injector, runInInjectionContext } from '@angular/core';
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
  stdin: { contents: `export {AppComponent} from './src/app/app.component'; export {QueueApiService} from './src/app/queue-api.service'; export {RealtimeService} from './src/app/realtime.service';`, resolveDir: root },
  tsconfig: path.join(root, 'tsconfig.json'), bundle: true, packages: 'external', platform: 'node', format: 'esm', outfile: output,
});
const { AppComponent, QueueApiService, RealtimeService } = await import(pathToFileURL(output));

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
  const injector = Injector.create({providers: [{provide: QueueApiService, useValue: api}, {provide: RealtimeService, useValue: realtime}]});
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
