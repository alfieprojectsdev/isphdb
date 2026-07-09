// Pure geo helpers for the traceroute-hop map overlay. No DOM, no I/O — unit-tested.

// Heat colors, identical to the latency chart / status cards in status.mjs.
export const GOOD_COLOR = '#3fb950';
export const WARN_COLOR = '#d29922';
export const BAD_COLOR = '#f85149';

function ipToInt(ip) {
  if (typeof ip !== 'string') return null;
  const parts = ip.split('.');
  if (parts.length !== 4) return null;
  let n = 0;
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part)) return null;
    const octet = Number(part);
    if (octet > 255) return null;
    n = n * 256 + octet;
  }
  return n >>> 0;
}

function inCidr(ip, cidr) {
  const [net, bitsStr] = cidr.split('/');
  const bits = Number(bitsStr);
  if (!Number.isInteger(bits) || bits < 0 || bits > 32) return false;
  const ipN = ipToInt(ip);
  const netN = ipToInt(net);
  if (ipN === null || netN === null) return false;
  if (bits === 0) return true;
  const mask = bits === 32 ? 0xffffffff : (~((1 << (32 - bits)) - 1)) >>> 0;
  return (ipN & mask) === (netN & mask);
}

function validEntry(entry) {
  return entry && typeof entry.lat === 'number' && typeof entry.lon === 'number';
}

/**
 * Resolve an IP to its {lat, lon, label} via exact match first, then CIDR-prefix match.
 * Returns null for unknown IPs. Non-object table values (e.g. the "_comment" key) and
 * keys without a '/' are ignored during the CIDR pass.
 */
export function lookupHopGeo(ip, table) {
  if (!ip || !table || typeof table !== 'object') return null;
  if (Object.prototype.hasOwnProperty.call(table, ip) && validEntry(table[ip])) {
    return table[ip];
  }
  for (const key of Object.keys(table)) {
    if (key.includes('/') && inCidr(ip, key) && validEntry(table[key])) {
      return table[key];
    }
  }
  return null;
}

/**
 * Map a latency (ms) to the heat color, matching status.mjs thresholds:
 * <=75 good, <=150 warn, else bad. The -1.0 / 500 failure sentinel maps to offline red.
 */
export function latencyToColor(latency) {
  if (latency === null || latency === undefined || latency < 0 || latency >= 500) {
    return BAD_COLOR; // offline / unreachable sentinel
  }
  if (latency > 150) return BAD_COLOR;
  if (latency > 75) return WARN_COLOR;
  return GOOD_COLOR;
}
