import { test } from 'node:test';
import assert from 'node:assert/strict';
import { lookupHopGeo, latencyToColor, tierColor, GOOD_COLOR, WARN_COLOR, BAD_COLOR, TIER_COLORS } from './geo.mjs';

const TABLE = {
  _comment: 'ignored',
  '1.2.3.4': { lat: 10, lon: 20, label: 'Exact' },
  '161.49.0.0/16': { lat: 14.65, lon: 121.03, label: 'Converge' },
  '172.69.0.0/16': { lat: 14.6, lon: 121.0, label: 'Cloudflare' },
};

// lookupHopGeo

test('lookupHopGeo: exact match wins', () => {
  assert.equal(lookupHopGeo('1.2.3.4', TABLE).label, 'Exact');
});

test('lookupHopGeo: CIDR prefix match', () => {
  assert.equal(lookupHopGeo('161.49.4.6', TABLE).label, 'Converge');
  assert.equal(lookupHopGeo('161.49.11.229', TABLE).label, 'Converge');
  assert.equal(lookupHopGeo('172.69.117.55', TABLE).label, 'Cloudflare');
});

test('lookupHopGeo: unknown IP -> null', () => {
  assert.equal(lookupHopGeo('8.8.8.8', TABLE), null);
});

test('lookupHopGeo: just-outside the /16 -> null', () => {
  assert.equal(lookupHopGeo('161.50.0.1', TABLE), null);
});

test('lookupHopGeo: null/garbage inputs -> null', () => {
  assert.equal(lookupHopGeo(null, TABLE), null);
  assert.equal(lookupHopGeo('not-an-ip', TABLE), null);
  assert.equal(lookupHopGeo('1.2.3.4', null), null);
});

test('lookupHopGeo: never returns the _comment string entry', () => {
  // A hop that matches nothing must not accidentally return the _comment value.
  assert.equal(lookupHopGeo('203.0.113.1', TABLE), null);
});

// latencyToColor

test('latencyToColor: good/warn/bad at status.mjs thresholds', () => {
  assert.equal(latencyToColor(75), GOOD_COLOR);
  assert.equal(latencyToColor(76), WARN_COLOR);
  assert.equal(latencyToColor(150), WARN_COLOR);
  assert.equal(latencyToColor(151), BAD_COLOR);
});

test('latencyToColor: sentinel latency -> offline red', () => {
  assert.equal(latencyToColor(-1), BAD_COLOR);
  assert.equal(latencyToColor(500), BAD_COLOR);
  assert.equal(latencyToColor(null), BAD_COLOR);
});

// tierColor

test('tierColor: known tiers map to the palette', () => {
  assert.equal(tierColor('isp'), TIER_COLORS.isp);
  assert.equal(tierColor('external'), TIER_COLORS.external);
});

test('tierColor: unknown/missing tier -> neutral grey', () => {
  assert.equal(tierColor('nope'), '#8b949e');
  assert.equal(tierColor(undefined), '#8b949e');
});
