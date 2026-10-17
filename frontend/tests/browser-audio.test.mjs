import '@angular/compiler';
import { build } from 'esbuild';
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const temporary = await mkdtemp(path.join(root, 'node_modules/.audio-test-'));
after(() => rm(temporary, {recursive: true, force: true}));
const output = path.join(temporary, 'audio.mjs');
await build({entryPoints: [path.join(root, 'src/app/browser-audio.service.ts')], tsconfig: path.join(root, 'tsconfig.json'), bundle: true, packages: 'external', platform: 'node', format: 'esm', outfile: output});
const { BrowserAudioService } = await import(pathToFileURL(output));

function setup(t, decodeError) {
  const sources = [], sockets = [], reports = [];
  class AudioContext {
    state = 'running'; currentTime = 0; destination = {};
    async resume() {}
    createOscillator() {return {connect(node) {return node;}, start() {}, stop() {}};}
    createGain() {return {gain: {}, connect() {}};}
    async decodeAudioData(bytes) {if (decodeError) throw decodeError; return bytes;}
    createBufferSource() {
      const source = {connect(node) {return node;}, start() {sources.push(this);}, stop() {this.onended?.();}};
      return source;
    }
  }
  class WebSocket {
    static OPEN = 1; static CONNECTING = 0; readyState = 0;
    constructor() {sockets.push(this);}
    send(message) {reports.push(JSON.parse(message));}
    close() {this.readyState = 3; this.onclose?.({code: 1000});}
  }
  const originals = new Map();
  for (const [key, value] of Object.entries({AudioContext, WebSocket, window: {setInterval: () => 1, clearInterval() {}, setTimeout: () => 1, clearTimeout() {}}, location: {protocol: 'http:', host: 'localhost'}})) {
    originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
    Object.defineProperty(globalThis, key, {value, configurable: true, writable: true});
  }
  const service = new BrowserAudioService();
  t.after(() => {
    service.disable();
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key];
    }
  });
  return {service, sources, sockets, reports, tick: () => new Promise(resolve => setImmediate(resolve))};
}

async function sendTest(fixture, clips = ['one', 'two']) {
  await fixture.service.enable();
  const socket = fixture.sockets[0]; socket.readyState = 1; socket.onopen();
  socket.onmessage({data: JSON.stringify({type: 'audio.ready', diagnostic_id: 'test', clips: clips.map(btoa), repeat_count: 1})});
  await fixture.tick();
}

test('diagnostics confirm completion only after every queued clip finishes', async t => {
  const f = setup(t);
  await sendTest(f);
  assert.equal(f.sources.length, 1);
  assert.equal(f.reports.some(report => report.phase === 'completed'), false);
  f.sources[0].onended(); await f.tick();
  assert.equal(f.sources.length, 2);
  assert.equal(f.reports.some(report => report.phase === 'completed'), false);
  f.sources[1].onended(); await f.tick();
  assert.equal(f.reports.at(-1).phase, 'completed');
  assert.equal(f.reports.at(-1).test_id, 'test');
});

test('diagnostics preserve the exact browser decoder error', async t => {
  const error = new Error('Unsupported WAV format'); error.name = 'EncodingError';
  const f = setup(t, error);
  await sendTest(f);
  const failure = f.reports.find(report => report.phase === 'failed');
  assert.equal(failure.detail, 'EncodingError: Unsupported WAV format');
  assert.equal(f.service.enabled, false);
});

test('muting midway reports interruption rather than successful playback', async t => {
  const f = setup(t);
  await sendTest(f);
  f.service.disable(); await f.tick();
  assert.equal(f.sources.length, 1);
  assert.equal(f.reports.some(report => report.phase === 'completed'), false);
  assert.equal(f.reports.some(report => report.phase === 'failed'), true);
});
