import { test } from 'node:test';
import assert from 'node:assert/strict';
import { evaluateStatus, applyPingBlockedOverride } from './status.mjs';

// evaluateStatus tests

test('evaluateStatus: good for low latency', () => {
  assert.equal(evaluateStatus([4]).status, 'good');
});

test('evaluateStatus: warn when latest > 75', () => {
  assert.equal(evaluateStatus([76]).status, 'warn');
});

test('evaluateStatus: bad when latest > 150', () => {
  assert.equal(evaluateStatus([151]).status, 'bad');
});

test('evaluateStatus: offline when latest >= 500', () => {
  assert.equal(evaluateStatus([500]).status, 'offline');
});

test('evaluateStatus: good for pair form [timestamp, value]', () => {
  assert.equal(evaluateStatus([[1700000000000, 4]]).status, 'good');
});

test('evaluateStatus: unknown for empty array', () => {
  assert.equal(evaluateStatus([]).status, 'unknown');
});

test('evaluateStatus: 500 failure sentinels do not inflate avg (healthy when latest succeeds)', () => {
  // 18 blocked pings (500) then two real low samples; latest is healthy.
  const window = Array(18).fill(500).concat([3, 4]);
  assert.equal(evaluateStatus(window).status, 'good');
});

test('evaluateStatus: latest sentinel is offline even with prior successes', () => {
  const window = [3, 4, 500];
  assert.equal(evaluateStatus(window).status, 'offline');
});

// applyPingBlockedOverride tests

test('applyPingBlockedOverride: local and isp offline with dns good -> both become good', () => {
  const { local, isp } = applyPingBlockedOverride(
    { status: 'offline', msg: 'Disconnected' },
    { status: 'offline', msg: 'Disconnected' },
    { status: 'good', msg: 'Healthy' }
  );
  assert.equal(local.status, 'good');
  assert.equal(local.msg, 'Healthy (Ping Blocked)');
  assert.equal(isp.status, 'good');
});

test('applyPingBlockedOverride: dns offline -> local and isp stay offline', () => {
  const { local, isp } = applyPingBlockedOverride(
    { status: 'offline', msg: 'Disconnected' },
    { status: 'offline', msg: 'Disconnected' },
    { status: 'offline', msg: 'Disconnected' }
  );
  assert.equal(local.status, 'offline');
  assert.equal(isp.status, 'offline');
});
