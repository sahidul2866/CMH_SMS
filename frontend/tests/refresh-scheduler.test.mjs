import { test } from 'node:test';
import assert from 'node:assert/strict';
import { RefreshScheduler } from '../src/app/refresh-scheduler.ts';

test('a burst of local and realtime changes produces one request batch', t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const requests = [];
  const scheduler = new RefreshScheduler((indicator, done) => {
    requests.push(indicator);
    done();
    return () => {};
  });
  scheduler.request(false);
  scheduler.request(true);
  scheduler.request(false);
  t.mock.timers.tick(149);
  assert.equal(requests.length, 0);
  t.mock.timers.tick(1);
  assert.deepEqual(requests, [true]);
  t.mock.timers.tick(30000);
  assert.equal(requests.length, 1, 'a healthy idle connection causes no polling');
});

test('events during an in-flight batch produce exactly one trailing refresh', t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const completions = [];
  const scheduler = new RefreshScheduler((indicator, done) => {
    completions.push(done);
    return () => {};
  });
  scheduler.request();
  t.mock.timers.tick(150);
  for (let i = 0; i < 30; i++) scheduler.request();
  t.mock.timers.tick(30000);
  assert.equal(completions.length, 1, 'no overlapping requests');
  completions[0]();
  t.mock.timers.tick(150);
  assert.equal(completions.length, 2);
  completions[1]();
  t.mock.timers.tick(30000);
  assert.equal(completions.length, 2);
});

test('navigation or hiding the page cancels pending and active requests', t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let requests = 0;
  let cancelled = 0;
  let finish;
  const scheduler = new RefreshScheduler((indicator, done) => {
    requests++;
    finish = done;
    return () => { cancelled++; done(); };
  });
  scheduler.request();
  scheduler.cancel();
  t.mock.timers.tick(150);
  assert.equal(requests, 0);
  scheduler.request();
  t.mock.timers.tick(150);
  scheduler.request();
  scheduler.cancel();
  finish();
  t.mock.timers.tick(30000);
  assert.equal(cancelled, 1);
  assert.equal(requests, 1, 'stale completion cannot restart an old view');
  scheduler.request();
  t.mock.timers.tick(150);
  assert.equal(requests, 2, 'new view still refreshes');
  scheduler.cancel();
});

test('a synchronous cached result does not leave the scheduler locked', t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let requests = 0;
  const scheduler = new RefreshScheduler((indicator, done) => { requests++; done(); return () => {}; });
  scheduler.request();
  t.mock.timers.tick(150);
  scheduler.request();
  t.mock.timers.tick(150);
  assert.equal(requests, 2);
});
